"""SSO API Views (Phase 5C & Trinity Workshop SSO).

Endpoints:
- POST /api/v1/sso/launch/
- POST /api/v1/sso/validate/
- GET  /api/v1/sso/pilot-status/
"""

import hashlib
import secrets

from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration_hub.models import (
    ConnectorInstance,
    InstanceStatus,
    ProductSsoClient,
    SsoAuthorizationCode,
)
from apps.integration_hub.serializers import (
    SsoLaunchRequestSerializer,
    SsoValidateRequestSerializer,
)
from apps.integration_hub.sso_service import (
    get_m2m_connector_secret,
    issue_sso_authorization_code,
    validate_sso_authorization_code,
)
from apps.organizations.models import Organization
from apps.product_registry.models import Product


class SsoLaunchView(APIView):
    """POST /api/v1/sso/launch/

    Validates effective access via compute_user_tenant_effective_access,
    issues a short-lived hashed authorization code, and returns a redirect URL
    built only from the client's registered callback_uri.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SsoLaunchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product_id = data.get("product_id")
        product_code = data.get("product_code")

        product = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()
        elif product_code:
            product = Product.objects.filter(code=product_code).first()

        if not product:
            return Response(
                {"error": "PRODUCT_NOT_FOUND", "detail": "Product does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve tenant organization from request data or active context
        org_id = data.get("organization_id")
        if not org_id:
            active_context = getattr(request.user, "active_context", None)
            if isinstance(active_context, dict) and active_context.get("organization"):
                org_id = active_context["organization"].get("id")

        if not org_id:
            # Fallback to user's first active membership organization
            first_membership = request.user.organization_memberships.filter(status="active").first()
            if first_membership:
                org_id = first_membership.organization_id

        if not org_id:
            return Response(
                {"error": "TENANT_CONTEXT_REQUIRED", "detail": "Organization context is required for SSO launch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = Organization.objects.filter(id=org_id).first()
        if not organization:
            return Response(
                {"error": "ORGANIZATION_NOT_FOUND", "detail": "Organization does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = issue_sso_authorization_code(
            user=request.user,
            organization=organization,
            product=product,
            redirect_uri=data.get("redirect_uri") or None,
            code_challenge=data.get("code_challenge") or None,
            code_challenge_method=data.get("code_challenge_method", "S256"),
            state=data.get("state") or None,
        )

        return Response(
            {
                "redirect_url": result["redirect_url"],
                "expires_at": result["expires_at"].isoformat(),
            },
            status=status.HTTP_200_OK,
        )


class SsoValidateView(APIView):
    """POST /api/v1/sso/validate/

    Product-side code exchange: server-to-server M2M Bearer authentication,
    single-use atomic check-and-mark, expiration verification, PKCE verification,
    and claims return.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        # 1. Server-to-server M2M Bearer authentication
        auth_header = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.strip():
            return Response(
                {"error": "AUTHENTICATION_REQUIRED", "detail": "Missing Authorization header."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": 'Bearer realm="sso_validate"'},
            )

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return Response(
                {"error": "INVALID_TOKEN_HEADER", "detail": "Authorization header must be 'Bearer <secret>'."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": 'Bearer realm="sso_validate"'},
            )

        provided_secret = parts[1]

        # 2. Validate request payload
        serializer = SsoValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client_identifier = data.get("client_identifier") or data.get("client_id")
        code = data["code"]

        # Peek at authorization code to identify client / product if not supplied
        product_code = None
        if not client_identifier:
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            sso_code_peek = (
                SsoAuthorizationCode.objects.filter(code_hash=code_hash)
                .select_related("product", "sso_client")
                .first()
            )
            if sso_code_peek:
                product_code = sso_code_peek.product.code
                client_identifier = sso_code_peek.sso_client.client_identifier

        try:
            expected_secret = get_m2m_connector_secret(
                product_code=product_code,
                client_identifier=client_identifier,
            )
        except exceptions.AuthenticationFailed as exc:
            return Response(exc.detail, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not secrets.compare_digest(provided_secret, expected_secret):
            return Response(
                {"error": "FORBIDDEN", "detail": "Invalid M2M connector secret."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3. Exchange code and resolve claims
        claims = validate_sso_authorization_code(
            code=code,
            client_identifier=client_identifier,
            code_verifier=data.get("code_verifier") or None,
            expected_org_id=data.get("expected_org_id") or None,
            expected_product_id=data.get("expected_product_id") or None,
            state=data.get("state") or None,
        )

        return Response(claims, status=status.HTTP_200_OK)


class SsoPilotStatusView(APIView):
    """GET /api/v1/sso/pilot-status/?product_id=<id>&organization_id=<org_id>

    Authoritatively evaluates if SSO is enabled for the product and optional organization.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        product_id = request.query_params.get("product_id")
        organization_id = request.query_params.get("organization_id")
        if not product_id:
            return Response({"sso_enabled": False}, status=status.HTTP_200_OK)

        sso_client = ProductSsoClient.objects.filter(
            product_id=product_id,
            is_active=True,
        ).first()

        instance_active = True
        if organization_id:
            instance_active = ConnectorInstance.objects.filter(
                connector__product_id=product_id,
                organization_id=organization_id,
                status=InstanceStatus.ACTIVE,
            ).exists()

        is_enabled = bool(sso_client and instance_active)

        return Response(
            {
                "product_id": product_id,
                "organization_id": organization_id,
                "sso_enabled": is_enabled,
                "client_identifier": sso_client.client_identifier if (sso_client and is_enabled) else None,
            },
            status=status.HTTP_200_OK,
        )
