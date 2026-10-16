"""SSO Service for LMS, Trinity Workshop, and FieldSense Operations Hub Integration.

Provides:
- Short-lived, single-use, PKCE-supported authorization code issuance.
- Strict redirect validation against registered callback URI (no wildcard, no client input override).
- HTTPS validation for non-local production callback URIs.
- Authoritative effective access verification via compute_user_tenant_effective_access.
- Cryptographically bound state generation and verification for CSRF protection.
- Atomic check-and-mark exchange and claims resolution.
- Per-client and per-product M2M secret resolution.
"""

import base64
import datetime
import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.assignments.constants import AccessState
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services.effective_access import compute_user_tenant_effective_access
from apps.integration_hub.models import (
    ConnectorInstance,
    InstanceStatus,
    ProductSsoClient,
    SsoAuthorizationCode,
)
from apps.organizations.models import Organization
from apps.product_registry.models import Product


def issue_sso_authorization_code(
    user: Any,
    organization: Organization,
    product: Product,
    redirect_uri: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: str = "S256",
    state: Optional[str] = None,
) -> dict[str, Any]:
    """Issues a short-lived authorization code for SSO launch.

    Verifies:
    1. Active SSO client exists for the target product.
    2. Active ConnectorInstance exists for this product and tenant organization.
    3. Registered callback_uri strictly matches redirect_uri (if provided).
    4. Enforces HTTPS for callback URI in non-local production environments.
    5. User has effective access to the product in the specified tenant organization.
    6. An active UserProductAssignment exists.
    7. Generates or cryptographically binds state/CSRF nonce.

    Returns:
    {
        "redirect_url": str,
        "expires_at": datetime,
    }
    """
    # 1. Lookup SSO client
    sso_client = ProductSsoClient.objects.filter(
        product=product,
        is_active=True,
    ).first()
    if not sso_client:
        raise exceptions.ValidationError(
            {"error": "SSO_NOT_CONFIGURED", "detail": "SSO client is not configured or active for this product."}
        )

    # 2. Check active connector instance for the tenant organization
    instance = ConnectorInstance.objects.filter(
        connector__product=product,
        organization=organization,
        status=InstanceStatus.ACTIVE,
    ).first()
    if not instance:
        raise exceptions.ValidationError(
            {
                "error": "INTEGRATION_NOT_CONFIGURED",
                "detail": "Organization does not have an active integration connector configured for this product.",
            }
        )

    # 3. Strict callback URI verification (reject any mismatch)
    parsed = urlparse(sso_client.callback_uri)
    is_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not getattr(settings, "DEBUG", False) and parsed.scheme != "https" and not is_local:
        raise exceptions.ValidationError(
            {"error": "INSECURE_CALLBACK_URI", "detail": "Callback URI must use HTTPS in production."}
        )

    if redirect_uri and redirect_uri != sso_client.callback_uri:
        raise exceptions.ValidationError(
            {"error": "REDIRECT_URI_MISMATCH", "detail": "Redirect URI does not match registered callback URI."}
        )

    # 4. Authoritative effective access verification
    effective_data = compute_user_tenant_effective_access(user, organization)
    entitled_prod_ids = {
        p.get("id")
        for p in effective_data.get("entitled_products", [])
        if p.get("access_state") == AccessState.AVAILABLE or p.get("is_entitled")
    }
    # Check if target product is authorized in effective access
    if str(product.id) not in entitled_prod_ids:
        matching_prod = next(
            (p for p in effective_data.get("products", []) if p.get("id") == str(product.id)),
            None,
        )
        denial = matching_prod.get("denial_code") if matching_prod else "ACCESS_DENIED"
        raise exceptions.PermissionDenied(
            {"error": "ACCESS_DENIED", "detail": f"User is not entitled to launch this product ({denial})."}
        )

    # 5. Active user product assignment
    assignment = UserProductAssignment.objects.filter(
        user=user,
        organization=organization,
        product=product,
        status=AssignmentStatus.ACTIVE,
    ).first()
    if not assignment:
        raise exceptions.PermissionDenied(
            {"error": "ASSIGNMENT_MISSING", "detail": "User has no active product assignment for this organization."}
        )

    # 6. Generate secure one-time code and its SHA-256 hash
    raw_code = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
    expires_at = timezone.now() + datetime.timedelta(minutes=5)

    # 7. Bind or generate state parameter
    bound_state = state
    if not bound_state:
        # Generate an HMAC-signed state bound to the client secret if available:
        # Format: <nonce>.<timestamp>.<hmac_sha256_hex>
        try:
            client_secret = get_m2m_connector_secret(
                product_code=product.code,
                client_identifier=sso_client.client_identifier,
            )
        except Exception:
            client_secret = ""

        if client_secret:
            nonce = secrets.token_urlsafe(16)
            ts = int(time.time())
            msg = f"{nonce}.{ts}".encode("utf-8")
            sig = hmac.new(client_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
            bound_state = f"{nonce}.{ts}.{sig}"
        else:
            bound_state = secrets.token_urlsafe(32)

    SsoAuthorizationCode.objects.create(
        user=user,
        organization=organization,
        product=product,
        assignment=assignment,
        sso_client=sso_client,
        code_hash=code_hash,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method or "S256",
        state=bound_state,
        expires_at=expires_at,
    )

    # 8. Build redirect URL strictly from client's registered callback_uri
    query_params = dict(parse_qsl(parsed.query))
    query_params["code"] = raw_code
    if bound_state:
        query_params["state"] = bound_state
    new_query = urlencode(query_params)
    redirect_url = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )

    return {
        "redirect_url": redirect_url,
        "expires_at": expires_at,
    }


def validate_sso_authorization_code(
    code: str,
    client_identifier: Optional[str] = None,
    code_verifier: Optional[str] = None,
    expected_org_id: Optional[str] = None,
    expected_product_id: Optional[str] = None,
    state: Optional[str] = None,
) -> dict[str, Any]:
    """Validates an SSO authorization code and returns user/org claims.

    Atomically checks single-use, expiration, PKCE, state/CSRF match,
    tenant/product binding, and confirms that user's assignment is still active.
    """
    if not code:
        raise exceptions.ValidationError(
            {"error": "CODE_REQUIRED", "detail": "Authorization code is required."}
        )

    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

    with transaction.atomic():
        sso_code = (
            SsoAuthorizationCode.objects.select_for_update()
            .select_related("user", "organization", "product", "assignment", "sso_client")
            .filter(code_hash=code_hash)
            .first()
        )
        if not sso_code:
            raise exceptions.ValidationError(
                {"error": "INVALID_CODE", "detail": "Authorization code is invalid."}
            )

        # 1. Single-use check
        if sso_code.used_at is not None:
            raise exceptions.ValidationError(
                {"error": "CODE_ALREADY_USED", "detail": "Authorization code has already been used."}
            )

        # 2. Expiration check
        if sso_code.expires_at < timezone.now():
            raise exceptions.ValidationError(
                {"error": "CODE_EXPIRED", "detail": "Authorization code has expired."}
            )

        # 3. Client identifier binding check
        if client_identifier and sso_code.sso_client.client_identifier != client_identifier:
            raise exceptions.ValidationError(
                {"error": "CLIENT_MISMATCH", "detail": "Code was not issued to this client."}
            )

        # 4. State parameter binding check (if provided during validation)
        if state is not None:
            if not sso_code.state or not secrets.compare_digest(sso_code.state, state):
                raise exceptions.ValidationError(
                    {"error": "STATE_MISMATCH", "detail": "Provided state does not match launch state."}
                )

        # 5. Tenant and product binding check
        if expected_org_id and str(sso_code.organization_id) != str(expected_org_id):
            raise exceptions.ValidationError(
                {"error": "TENANT_MISMATCH", "detail": "Code tenant binding mismatch."}
            )
        if expected_product_id and str(sso_code.product_id) != str(expected_product_id):
            raise exceptions.ValidationError(
                {"error": "PRODUCT_MISMATCH", "detail": "Code product binding mismatch."}
            )

        # 6. PKCE verification
        if sso_code.code_challenge:
            if not code_verifier:
                raise exceptions.ValidationError(
                    {"error": "PKCE_VERIFIER_REQUIRED", "detail": "Code verifier is required."}
                )
            if sso_code.code_challenge_method == "S256":
                # RFC 7636: BASE64URL-ENCODE(SHA256(ASCII(code_verifier))) without padding
                digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
                computed_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
                if computed_challenge != sso_code.code_challenge:
                    raise exceptions.ValidationError(
                        {"error": "PKCE_VERIFICATION_FAILED", "detail": "PKCE challenge verification failed."}
                    )
            elif sso_code.code_challenge_method == "plain":
                if code_verifier != sso_code.code_challenge:
                    raise exceptions.ValidationError(
                        {"error": "PKCE_VERIFICATION_FAILED", "detail": "PKCE challenge verification failed."}
                    )

        # 7. Assignment revocation check (assignment revoked before validate)
        sso_code.assignment.refresh_from_db()
        if sso_code.assignment.status != AssignmentStatus.ACTIVE:
            raise exceptions.PermissionDenied(
                {"error": "ASSIGNMENT_REVOKED", "detail": "User product assignment has been revoked or suspended."}
            )

        # 8. Atomic mark used
        sso_code.used_at = timezone.now()
        sso_code.save(update_fields=["used_at"])

    # 9. Assemble returned verified claims
    return {
        "user": {
            "id": str(sso_code.user.id),
            "email": sso_code.user.email,
            "username": getattr(sso_code.user, "username", sso_code.user.email),
            "full_name": getattr(sso_code.user, "full_name", sso_code.user.email),
        },
        "organization": {
            "id": str(sso_code.organization.id),
            "code": sso_code.organization.code,
            "name": sso_code.organization.name,
        },
        "product": {
            "id": str(sso_code.product.id),
            "code": sso_code.product.code,
            "name": sso_code.product.name,
        },
        "assignment_id": str(sso_code.assignment_id),
        "audience": sso_code.sso_client.audience,
    }


def is_fieldsense_client(
    client_identifier: Optional[str] = None,
    product_code: Optional[str] = None,
) -> bool:
    """Checks whether the client identifier or product code corresponds to FieldSense Operations Hub."""
    client_id_lower = (client_identifier or "").lower().strip()
    prod_code_lower = (product_code or "").lower().strip()

    if client_id_lower == "fieldsense-ops-hub" or "fieldsense" in client_id_lower:
        return True
    if prod_code_lower in ("fieldsense", "fieldsense-ops-hub"):
        return True
    if client_identifier:
        try:
            sso_client = (
                ProductSsoClient.objects.filter(client_identifier=client_identifier)
                .select_related("product")
                .first()
            )
            if sso_client and sso_client.product and sso_client.product.code in ("fieldsense", "fieldsense-ops-hub"):
                return True
        except Exception:
            pass
    return False


def is_trinity_client(
    client_identifier: Optional[str] = None,
    product_code: Optional[str] = None,
) -> bool:
    """Checks whether the client identifier or product code corresponds to Trinity Workshop."""
    client_id_lower = (client_identifier or "").lower().strip()
    prod_code_lower = (product_code or "").lower().strip()

    if client_id_lower == "trinity-workshop-app" or "trinity" in client_id_lower:
        return True
    if prod_code_lower in ("workshop-trinity", "workshop"):
        return True
    if client_identifier:
        try:
            sso_client = (
                ProductSsoClient.objects.filter(client_identifier=client_identifier)
                .select_related("product")
                .first()
            )
            if sso_client and sso_client.product and sso_client.product.code in ("workshop-trinity", "workshop"):
                return True
        except Exception:
            pass
    return False


def get_m2m_connector_secret(
    product_code: Optional[str] = None,
    client_identifier: Optional[str] = None,
) -> str:
    """Retrieves the configured M2M secret for backend-to-backend authentication.

    Per-client and per-product secret isolation:
    - FieldSense Operations Hub ('fieldsense-ops-hub' / 'fieldsense'):
        Uses ONLY VIBECONNECT_FIELDSENSE_M2M_SECRET. Fails closed if missing.
        Never falls back to Trinity, LMS, or any shared secret.
    - Trinity Workshop ('trinity-workshop-app' / 'workshop-trinity'):
        Loads VIBECONNECT_TRINITY_M2M_SECRET with fallback to VIBECONNECT_M2M_SECRET.
    - LMS / Default ('pilot_lms_client' / 'lms' / other clients):
        Loads VIBECONNECT_LMS_M2M_SECRET with fallback to VIBECONNECT_M2M_SECRET.

    Never exposes or logs secret values.
    Raises exceptions.AuthenticationFailed if not configured.
    """
    if is_fieldsense_client(client_identifier=client_identifier, product_code=product_code):
        secret = (
            getattr(settings, "VIBECONNECT_FIELDSENSE_M2M_SECRET", None)
            or os.environ.get("VIBECONNECT_FIELDSENSE_M2M_SECRET", "")
        ).strip()
        if not secret:
            raise exceptions.AuthenticationFailed(
                {
                    "error": "SERVER_MISCONFIGURED",
                    "detail": "FieldSense M2M connector secret is not configured on the server.",
                }
            )
        return secret

    if is_trinity_client(client_identifier=client_identifier, product_code=product_code):
        secret = (
            getattr(settings, "VIBECONNECT_TRINITY_M2M_SECRET", None)
            or os.environ.get("VIBECONNECT_TRINITY_M2M_SECRET", "")
        ).strip()
    else:
        secret = (
            getattr(settings, "VIBECONNECT_LMS_M2M_SECRET", None)
            or os.environ.get("VIBECONNECT_LMS_M2M_SECRET", "")
        ).strip()

    if not secret:
        secret = (
            getattr(settings, "VIBECONNECT_M2M_SECRET", None)
            or os.environ.get("VIBECONNECT_M2M_SECRET", "")
        ).strip()

    if not secret:
        raise exceptions.AuthenticationFailed(
            {"error": "SERVER_MISCONFIGURED", "detail": "M2M connector secret is not configured on the server."}
        )
    return secret
