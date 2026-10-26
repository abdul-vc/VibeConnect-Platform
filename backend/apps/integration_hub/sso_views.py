"""SSO API Views (Phase 5C, Trinity Workshop & FieldSense Operations Hub SSO).

Endpoints:
- POST /api/v1/sso/launch/
- POST /api/v1/sso/validate/
- GET  /api/v1/sso/pilot-status/
"""

import logging
import secrets

logger = logging.getLogger(__name__)

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
    LmsLaunchGrantForbiddenError,
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

            membership = OrganizationMembership.objects.filter(
                organization=organization,
                user=request.user,
                status="active",
            ).first()
            is_tenant_admin = bool(
                membership and (
                    membership.membership_type == MembershipType.TENANT_ADMIN
                    or (membership.role and getattr(membership.role, "is_admin_role", False))
                    or (membership.role and getattr(membership.role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                    or (membership.role and getattr(membership.role, "name", "") == "Tenant Administrator")
                )
            )

            if not is_tenant_admin:
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
                    quiz_target_path = "/admin" if is_tenant_admin else "/dashboard"

                    grant = request_quiz_launch_grant(
                        user_id=str(request.user.id),
                        tenant_id=str(organization.id),
                        email=getattr(request.user, "email", "") or "",
                        first_name=first_name,
                        last_name=last_name,
                        phone=getattr(request.user, "phone", "") or "",
                        context="standard",
                        target_path=quiz_target_path,
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

                membership = OrganizationMembership.objects.filter(
                    organization=organization,
                    user=request.user,
                    status="active",
                ).first()
                is_tenant_admin = bool(
                    membership and (
                        membership.membership_type == MembershipType.TENANT_ADMIN
                        or (membership.role and getattr(membership.role, "is_admin_role", False))
                        or (membership.role and getattr(membership.role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                        or (membership.role and getattr(membership.role, "name", "") == "Tenant Administrator")
                    )
                )

                assignment = UserProductAssignment.objects.filter(
                    user=request.user,
                    organization=organization,
                    product=product,
                    status=AssignmentStatus.ACTIVE,
                ).first()

                if not is_tenant_admin and not assignment:
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

                # Authoritative LMS console resolution based on persisted assignment configuration
                chosen_console = assignment.launch_console if (assignment and assignment.launch_console) else None
                if chosen_console == "tenant_console":
                    if not is_tenant_admin:
                        raise exceptions.PermissionDenied(
                            {"error": "FORBIDDEN_CONSOLE", "detail": "Tenant Console requires administrative privileges."}
                        )
                    target_route = "/org-admin"
                elif chosen_console == "normal_user_console":
                    target_route = "/dashboard"
                else:
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
                    target_user_id = str(request.user.id)
                    user_mapping = ExternalUserMapping.objects.filter(
                        organization=organization,
                        user=request.user,
                        status=ExternalUserMappingStatus.ACTIVE,
                    ).first()
                    if user_mapping and user_mapping.external_user_id and user_mapping.external_user_id.startswith("tenant_"):
                        target_user_id = user_mapping.external_user_id

                    try:
                        grant = request_lms_launch_grant(
                            external_tenant_id=str(organization.id),
                            external_user_id=target_user_id,
                            context="standard",
                            target_route=target_route,
                        )
                    except LmsLaunchGrantNotFoundError:
                        # Upstream mapping missing; execute idempotent provisioning and retry
                        provision_tenant_to_lms(organization)
                        provision_user_to_lms(request.user, organization)
                        grant = request_lms_launch_grant(
                            external_tenant_id=str(organization.id),
                            external_user_id=target_user_id,
                            context="standard",
                            target_route=target_route,
                        )
                    except LmsLaunchGrantForbiddenError as exc:
                        if "Platform super administrators cannot be launched" not in str(exc):
                            raise

                        tenant_ext_uid = f"tenant_{organization.id}_{request.user.id}"
                        clean_email = f"member.{str(request.user.id)[:8]}@{organization.code}.demo.internal"
                        from apps.integration_hub.lms_connector import LmsConnectorClient
                        client = LmsConnectorClient()
                        first_name = getattr(request.user, "first_name", "") or ""
                        last_name = getattr(request.user, "last_name", "") or ""
                        full_name = getattr(request.user, "full_name", "") or ""
                        if not first_name and full_name:
                            parts = full_name.strip().split(" ", 1)
                            first_name = parts[0]
                            last_name = parts[1] if len(parts) > 1 else ""

                        payload = {
                            "external_tenant_id": str(organization.id),
                            "external_user_id": tenant_ext_uid,
                            "email": clean_email,
                            "first_name": first_name or "Member",
                            "last_name": last_name or "User",
                            "role": "organization_admin" if (is_tenant_admin and target_route == "/org-admin") else "member",
                            "is_active": True,
                        }
                        client.provision_user(payload)
                        if user_mapping:
                            user_mapping.external_user_id = tenant_ext_uid
                            user_mapping.save(update_fields=["external_user_id", "updated_at"])

                        grant = request_lms_launch_grant(
                            external_tenant_id=str(organization.id),
                            external_user_id=tenant_ext_uid,
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

        if product.code in ("crm", "salestracker", "sales_tracker", "sales-tracker", "salestracker_crm"):
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

            membership = OrganizationMembership.objects.filter(
                organization=organization,
                user=request.user,
                status="active",
            ).first()
            is_tenant_admin = bool(
                membership and (
                    membership.membership_type == MembershipType.TENANT_ADMIN
                    or (membership.role and getattr(membership.role, "is_admin_role", False))
                    or (membership.role and getattr(membership.role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                    or (membership.role and getattr(membership.role, "name", "") == "Tenant Administrator")
                )
            )

            if not is_tenant_admin:
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

            from apps.integration_hub.salestracker_sso_client import (
                is_salestracker_sso_configured,
                request_salestracker_launch_grant,
                get_salestracker_superadmin_employee_id,
                get_salestracker_frontend_url,
                SalesTrackerSsoAuthError,
                SalesTrackerSsoForbiddenError,
                SalesTrackerSsoNotFoundError,
                SalesTrackerSsoConflictError,
                SalesTrackerSsoConnectionError,
                SalesTrackerSsoError,
            )

            if is_salestracker_sso_configured():
                try:
                    emp_id = get_salestracker_superadmin_employee_id()
                    target_route = "/dashboard"

                    grant = request_salestracker_launch_grant(
                        employee_id=emp_id,
                        context="showcase",
                        target_route=target_route,
                    )
                    expires_in = grant.get("expires_in", 60)
                    return Response(
                        {
                            "redirect_url": grant["callback_url"],
                            "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
                            "direct_launch": False,
                        },
                        status=status.HTTP_200_OK,
                    )
                except SalesTrackerSsoAuthError:
                    return Response(
                        {"error": "SALESTRACKER_SSO_UNAUTHORIZED", "detail": "Sales Tracker SSO M2M authentication failed."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except SalesTrackerSsoForbiddenError as exc:
                    return Response(
                        {"error": "SALESTRACKER_ACCESS_DENIED", "detail": exc.detail or exc.message},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                except SalesTrackerSsoNotFoundError as exc:
                    return Response(
                        {"error": "SALESTRACKER_USER_NOT_FOUND", "detail": exc.detail or exc.message},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except SalesTrackerSsoConflictError as exc:
                    return Response(
                        {"error": "SALESTRACKER_ACCOUNT_CONFLICT", "detail": exc.message},
                        status=status.HTTP_409_CONFLICT,
                    )
                except SalesTrackerSsoConnectionError as exc:
                    demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
                    fallback_url = demo_env.base_url if demo_env else (get_salestracker_frontend_url() or "http://localhost:5173")
                    logger.warning("Sales Tracker server unreachable: falling back to demo URL %s (%s)", fallback_url, exc.message)
                    return Response(
                        {
                            "redirect_url": fallback_url,
                            "expires_at": (timezone.now() + timedelta(minutes=5)).isoformat(),
                            "direct_launch": True,
                        },
                        status=status.HTTP_200_OK,
                    )
                except SalesTrackerSsoError as exc:
                    return Response(
                        {"error": "SALESTRACKER_SSO_FAILED", "detail": exc.message},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
            direct_url = demo_env.base_url if demo_env else (get_salestracker_frontend_url() or "http://localhost:5173")
            return Response(
                {
                    "redirect_url": direct_url,
                    "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                    "direct_launch": True,
                },
                status=status.HTTP_200_OK,
            )

        if product.code in ("divineconnect", "divine_connect", "divine-connect", "events", "event"):
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

            membership = OrganizationMembership.objects.filter(
                organization=organization,
                user=request.user,
                status="active",
            ).first()
            is_tenant_admin = bool(
                membership and (
                    membership.membership_type == MembershipType.TENANT_ADMIN
                    or (membership.role and getattr(membership.role, "is_admin_role", False))
                    or (membership.role and getattr(membership.role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                    or (membership.role and getattr(membership.role, "name", "") == "Tenant Administrator")
                )
            )

            if not is_tenant_admin:
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

            from apps.integration_hub.divineconnect_sso_client import (
                is_divineconnect_sso_configured,
                request_divineconnect_launch_grant,
                get_divineconnect_admin_username,
                get_divineconnect_admin_email,
                get_divineconnect_frontend_url,
                DivineConnectSsoAuthError,
                DivineConnectSsoForbiddenError,
                DivineConnectSsoNotFoundError,
                DivineConnectSsoConflictError,
                DivineConnectSsoConnectionError,
                DivineConnectSsoError,
            )

            if is_divineconnect_sso_configured():
                try:
                    admin_user = get_divineconnect_admin_username()
                    admin_email = get_divineconnect_admin_email()

                    grant = request_divineconnect_launch_grant(
                        username=admin_user,
                        email=admin_email,
                        context="showcase",
                        target_route="/admin",
                    )
                    expires_in = grant.get("expires_in", 60)
                    return Response(
                        {
                            "redirect_url": grant["callback_url"],
                            "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
                            "direct_launch": False,
                        },
                        status=status.HTTP_200_OK,
                    )
                except DivineConnectSsoAuthError:
                    return Response(
                        {"error": "DIVINECONNECT_SSO_UNAUTHORIZED", "detail": "Divine Connect SSO M2M authentication failed."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except DivineConnectSsoForbiddenError as exc:
                    return Response(
                        {"error": "DIVINECONNECT_ACCESS_DENIED", "detail": exc.detail or exc.message},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                except DivineConnectSsoNotFoundError as exc:
                    return Response(
                        {"error": "DIVINECONNECT_USER_NOT_FOUND", "detail": exc.detail or exc.message},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except DivineConnectSsoConflictError as exc:
                    return Response(
                        {"error": "DIVINECONNECT_ACCOUNT_CONFLICT", "detail": exc.message},
                        status=status.HTTP_409_CONFLICT,
                    )
                except DivineConnectSsoConnectionError as exc:
                    demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
                    fallback_url = demo_env.base_url if demo_env else (get_divineconnect_frontend_url() or "http://localhost:8080")
                    logger.warning("Divine Connect server unreachable: falling back to demo URL %s (%s)", fallback_url, exc.message)
                    return Response(
                        {
                            "redirect_url": fallback_url,
                            "expires_at": (timezone.now() + timedelta(minutes=5)).isoformat(),
                            "direct_launch": True,
                        },
                        status=status.HTTP_200_OK,
                    )
                except DivineConnectSsoError as exc:
                    return Response(
                        {"error": "DIVINECONNECT_SSO_FAILED", "detail": exc.message},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
            direct_url = demo_env.base_url if demo_env else (get_divineconnect_frontend_url() or "http://localhost:8080")
            return Response(
                {
                    "redirect_url": direct_url,
                    "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                    "direct_launch": True,
                },
                status=status.HTTP_200_OK,
            )

        if product.code in ("workhub", "work_hub", "work-hub"):
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

            membership = OrganizationMembership.objects.filter(
                organization=organization,
                user=request.user,
                status="active",
            ).first()
            is_tenant_admin = bool(
                membership and (
                    membership.membership_type == MembershipType.TENANT_ADMIN
                    or (membership.role and getattr(membership.role, "is_admin_role", False))
                    or (membership.role and getattr(membership.role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                    or (membership.role and getattr(membership.role, "name", "") == "Tenant Administrator")
                )
            )

            if not is_tenant_admin:
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

            from apps.integration_hub.workhub_sso_client import (
                is_workhub_sso_configured,
                request_workhub_launch_grant,
                get_workhub_admin_username,
                get_workhub_frontend_url,
                WorkHubSsoAuthError,
                WorkHubSsoForbiddenError,
                WorkHubSsoNotFoundError,
                WorkHubSsoConflictError,
                WorkHubSsoConnectionError,
                WorkHubSsoError,
            )

            if is_workhub_sso_configured():
                try:
                    admin_user = get_workhub_admin_username()

                    grant = request_workhub_launch_grant(
                        username=admin_user,
                        context="showcase",
                        target_route="/admin",
                    )
                    expires_in = grant.get("expires_in", 60)
                    return Response(
                        {
                            "redirect_url": grant["callback_url"],
                            "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
                            "direct_launch": False,
                        },
                        status=status.HTTP_200_OK,
                    )
                except WorkHubSsoAuthError:
                    return Response(
                        {"error": "WORKHUB_SSO_UNAUTHORIZED", "detail": "WorkHub SSO M2M authentication failed."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except WorkHubSsoForbiddenError as exc:
                    return Response(
                        {"error": "WORKHUB_ACCESS_DENIED", "detail": exc.detail or exc.message},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                except WorkHubSsoNotFoundError as exc:
                    return Response(
                        {"error": "WORKHUB_USER_NOT_FOUND", "detail": exc.detail or exc.message},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except WorkHubSsoConflictError as exc:
                    return Response(
                        {"error": "WORKHUB_ACCOUNT_CONFLICT", "detail": exc.message},
                        status=status.HTTP_409_CONFLICT,
                    )
                except WorkHubSsoConnectionError as exc:
                    demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
                    fallback_url = demo_env.base_url if demo_env else (get_workhub_frontend_url() or "http://localhost:6395")
                    logger.warning("WorkHub server unreachable: falling back to demo URL %s (%s)", fallback_url, exc.message)
                    return Response(
                        {
                            "redirect_url": fallback_url,
                            "expires_at": (timezone.now() + timedelta(minutes=5)).isoformat(),
                            "direct_launch": True,
                        },
                        status=status.HTTP_200_OK,
                    )
                except WorkHubSsoError as exc:
                    return Response(
                        {"error": "WORKHUB_SSO_FAILED", "detail": exc.message},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            demo_env = ProductDemoEnvironment.objects.filter(product=product, is_active=True).first()
            direct_url = demo_env.base_url if demo_env else (get_workhub_frontend_url() or "http://localhost:6395")
            return Response(
                {
                    "redirect_url": direct_url,
                    "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                    "direct_launch": True,
                },
                status=status.HTTP_200_OK,
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
        product_code = None

        if not client_identifier:
            raw_code = data.get("code")
            if raw_code:
                import hashlib
                from apps.integration_hub.models import SsoAuthorizationCode
                code_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
                auth_code_obj = (
                    SsoAuthorizationCode.objects.filter(code_hash=code_hash)
                    .select_related("product", "sso_client")
                    .first()
                )
                if auth_code_obj:
                    if auth_code_obj.sso_client:
                        client_identifier = auth_code_obj.sso_client.client_identifier
                    if auth_code_obj.product:
                        product_code = auth_code_obj.product.code

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
            code=data["code"],
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
