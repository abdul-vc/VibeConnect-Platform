"""SSO API Views (Phase 5C).

Endpoints:
- POST /api/v1/sso/launch/
- POST /api/v1/sso/validate/
- GET  /api/v1/sso/pilot-status/
"""

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
from apps.integration_hub.lifecycle_service import is_lms_product
from apps.integration_hub.lms_launch_grant_client import (
    LmsLaunchGrantAuthError,
    LmsLaunchGrantConflictError,
    LmsLaunchGrantError,
    LmsLaunchGrantNotFoundError,
    is_lms_launch_grant_configured,
    request_lms_launch_grant,
)
from apps.integration_hub.provisioning_service import (
    provision_tenant_to_lms,
    provision_user_to_lms,
)
from apps.organizations.models import MembershipType, Organization, OrganizationMembership
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

        product_id = data["product_id"]
        product = Product.objects.filter(id=product_id).first()
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

        if product.code == "quiz":
            from datetime import timedelta
            from django.utils import timezone
            from apps.assignments.constants import AccessState
            from apps.assignments.models import AssignmentStatus, UserProductAssignment
            from apps.assignments.services.effective_access import compute_user_tenant_effective_access
            from apps.showcase.models import ProductDemoEnvironment

            effective_data = compute_user_tenant_effective_access(request.user, organization)
            entitled_prod_ids = {
                p.get("id")
                for p in effective_data.get("entitled_products", [])
                if p.get("access_state") == AccessState.AVAILABLE or p.get("is_entitled")
            }
            if str(product.id) not in entitled_prod_ids:
                matching_prod = next(
                    (p for p in effective_data.get("products", []) if p.get("id") == str(product.id)),
                    None,
                )
                denial = matching_prod.get("denial_code") if matching_prod else "ACCESS_DENIED"
                raise exceptions.PermissionDenied(
                    {"error": "ACCESS_DENIED", "detail": f"User is not entitled to launch this product ({denial})."}
                )

            assignment = UserProductAssignment.objects.filter(
                user=request.user,
                organization=organization,
                product=product,
                status=AssignmentStatus.ACTIVE,
            ).first()
            if not assignment:
                raise exceptions.PermissionDenied(
                    {"error": "ASSIGNMENT_MISSING", "detail": "User has no active product assignment for this organization."}
                )

            from apps.integration_hub.quiz_sso_client import (
                is_quiz_sso_configured,
                request_quiz_launch_grant,
                QuizSsoAuthError,
                QuizSsoConflictError,
                QuizSsoError,
            )

            if is_quiz_sso_configured():
                try:
                    first_name = getattr(request.user, "first_name", "") or ""
                    last_name = getattr(request.user, "last_name", "") or ""
                    if not first_name:
                        full_name = getattr(request.user, "full_name", "") or ""
                        if full_name:
                            name_parts = full_name.strip().split(maxsplit=1)
                            first_name = name_parts[0]
                            last_name = name_parts[1] if len(name_parts) > 1 else ""

                    grant = request_quiz_launch_grant(
                        user_id=str(request.user.id),
                        tenant_id=str(organization.id),
                        email=getattr(request.user, "email", "") or "",
                        first_name=first_name,
                        last_name=last_name,
                        phone=getattr(request.user, "phone", "") or "",
                        context="standard",
                        target_path="/dashboard",
                    )
                    return Response(
                        {
                            "redirect_url": grant["callback_url"],
                            "expires_at": (timezone.now() + timedelta(minutes=5)).isoformat(),
                            "direct_launch": False,
                        },
                        status=status.HTTP_200_OK,
                    )
                except QuizSsoConflictError as exc:
                    return Response(
                        {"error": "QUIZ_ACCOUNT_CONFLICT", "detail": exc.message},
                        status=status.HTTP_409_CONFLICT,
                    )
                except QuizSsoAuthError as exc:
                    return Response(
                        {"error": "QUIZ_SSO_UNAUTHORIZED", "detail": "Quiz SSO M2M authentication failed."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except QuizSsoError as exc:
                    return Response(
                        {"error": "QUIZ_SSO_FAILED", "detail": exc.message},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
            direct_url = demo_env.base_url if demo_env else "https://quiz.digielvestech.in/"

            return Response(
                {
                    "redirect_url": direct_url,
                    "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                    "direct_launch": True,
                },
                status=status.HTTP_200_OK,
            )

        if is_lms_product(product):
            if is_lms_launch_grant_configured():
                from datetime import timedelta
                from django.utils import timezone
                from apps.assignments.constants import AccessState
                from apps.assignments.models import AssignmentStatus, UserProductAssignment
                from apps.assignments.services.effective_access import compute_user_tenant_effective_access

                effective_data = compute_user_tenant_effective_access(request.user, organization)
                entitled_prod_ids = {
                    p.get("id")
                    for p in effective_data.get("entitled_products", [])
                    if p.get("access_state") == AccessState.AVAILABLE or p.get("is_entitled")
                }
                if str(product.id) not in entitled_prod_ids:
                    matching_prod = next(
                        (p for p in effective_data.get("products", []) if p.get("id") == str(product.id)),
                        None,
                    )
                    denial = matching_prod.get("denial_code") if matching_prod else "ACCESS_DENIED"
                    raise exceptions.PermissionDenied(
                        {"error": "ACCESS_DENIED", "detail": f"User is not entitled to launch this product ({denial})."}
                    )

                assignment = UserProductAssignment.objects.filter(
                    user=request.user,
                    organization=organization,
                    product=product,
                    status=AssignmentStatus.ACTIVE,
                ).first()
                if not assignment:
                    raise exceptions.PermissionDenied(
                        {"error": "ASSIGNMENT_MISSING", "detail": "User has no active product assignment for this organization."}
                    )

                from apps.integration_hub.models import (
                    ExternalTenantMapping,
                    ExternalUserMapping,
                    ExternalUserMappingStatus,
                    ProvisioningJob,
                    ProvisioningJobStatus,
                )

                pending_job = ProvisioningJob.objects.filter(
                    organization=organization,
                    user__in=[None, request.user],
                    status__in=[ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING],
                ).first()
                if pending_job:
                    return Response(
                        {
                            "error": "PROVISIONING_PENDING",
                            "detail": "LMS provisioning is still in progress. Please try again shortly.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                membership = OrganizationMembership.objects.filter(
                    organization=organization,
                    user=request.user,
                    status="active",
                ).first()
                is_tenant_admin = bool(
                    membership and membership.membership_type == MembershipType.TENANT_ADMIN
                )
                target_route = "/org-admin" if is_tenant_admin else "/dashboard"

                has_tenant_mapping = ExternalTenantMapping.objects.filter(
                    organization=organization
                ).exists()
                has_user_mapping = ExternalUserMapping.objects.filter(
                    organization=organization,
                    user=request.user,
                    status=ExternalUserMappingStatus.ACTIVE,
                ).exists()

                if not (has_tenant_mapping and has_user_mapping):
                    try:
                        if not has_tenant_mapping:
                            provision_tenant_to_lms(organization)
                        if not has_user_mapping:
                            provision_user_to_lms(request.user, organization)
                    except Exception as exc:
                        return Response(
                            {
                                "error": "PROVISIONING_FAILED",
                                "detail": f"LMS provisioning failed: {exc}",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                try:
                    try:
                        grant = request_lms_launch_grant(
                            external_tenant_id=str(organization.id),
                            external_user_id=str(request.user.id),
                            context="standard",
                            target_route=target_route,
                        )
                    except LmsLaunchGrantNotFoundError:
                        # Upstream mapping missing; execute idempotent provisioning and retry
                        provision_tenant_to_lms(organization)
                        provision_user_to_lms(request.user, organization)
                        grant = request_lms_launch_grant(
                            external_tenant_id=str(organization.id),
                            external_user_id=str(request.user.id),
                            context="standard",
                            target_route=target_route,
                        )

                    expires_in = grant.get("expires_in", 60)
                    expires_at = (timezone.now() + timedelta(seconds=expires_in)).isoformat()
                    return Response(
                        {
                            "redirect_url": grant["callback_url"],
                            "expires_at": expires_at,
                            "direct_launch": False,
                        },
                        status=status.HTTP_200_OK,
                    )
                except LmsLaunchGrantConflictError as exc:
                    return Response(
                        {"error": "LMS_ACCOUNT_CONFLICT", "detail": exc.message},
                        status=status.HTTP_409_CONFLICT,
                    )
                except LmsLaunchGrantAuthError:
                    return Response(
                        {"error": "LMS_SSO_UNAUTHORIZED", "detail": "LMS SSO M2M authentication failed."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except LmsLaunchGrantError as exc:
                    return Response(
                        {"error": "LMS_SSO_FAILED", "detail": exc.message},
                        status=status.HTTP_502_BAD_GATEWAY,
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
        try:
            expected_secret = get_m2m_connector_secret(product_code="lms")
        except exceptions.AuthenticationFailed as exc:
            return Response(exc.detail, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not secrets.compare_digest(provided_secret, expected_secret):
            return Response(
                {"error": "FORBIDDEN", "detail": "Invalid M2M connector secret."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Validate request payload
        serializer = SsoValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 3. Exchange code and resolve claims
        claims = validate_sso_authorization_code(
            code=data["code"],
            client_identifier=data.get("client_identifier") or None,
            code_verifier=data.get("code_verifier") or None,
            expected_org_id=data.get("expected_org_id") or None,
            expected_product_id=data.get("expected_product_id") or None,
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

        product = Product.objects.filter(id=product_id).first()
        if product and product.code == "quiz":
            from apps.integration_hub.quiz_sso_client import is_quiz_sso_configured

            sso_configured = is_quiz_sso_configured()
            return Response(
                {
                    "product_id": product_id,
                    "organization_id": organization_id,
                    "sso_enabled": True,
                    "client_identifier": "quiz_sso" if sso_configured else "quiz_direct_launch",
                },
                status=status.HTTP_200_OK,
            )

        if product and is_lms_product(product):
            if is_lms_launch_grant_configured():
                return Response(
                    {
                        "product_id": product_id,
                        "organization_id": organization_id,
                        "sso_enabled": True,
                        "client_identifier": "lms_launch_grant",
                    },
                    status=status.HTTP_200_OK,
                )

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
