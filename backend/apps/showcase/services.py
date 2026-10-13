"""Product Showcase & Demo Hub Services – Phase 11.

Three services only: ProductShowcaseService, DemoEnvironmentService,
ShowcasePresentationService. No extra abstraction layers.
"""
from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseMedia,
    ProductShowcaseProfile,
    ShowcaseVisibility,
    validate_demo_url,
)

_HTTPS_RE = re.compile(r"^https://", re.IGNORECASE)

AUTHORIZED_DEMO_ORGANIZATION_CODES: frozenset[str] = frozenset({"boss-demo-org"})


def _check_url(url: str, field: str = "url") -> None:
    """Raise ValidationError for any non-https or dangerous URL."""
    try:
        validate_demo_url(url)
    except ValidationError as exc:
        raise ValidationError({field: exc.messages}) from exc


class ShowcaseServiceError(Exception):
    """Raised for business rule violations in the showcase domain."""


class ProductShowcaseService:
    """CRUD, publish/unpublish, reorder for ProductShowcaseProfile."""

    # ------------------------------------------------------------------
    # List / search
    # ------------------------------------------------------------------
    @staticmethod
    def list_profiles(
        *,
        search: str | None = None,
        visibility: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        qs = (
            ProductShowcaseProfile.objects.select_related("product", "created_by", "updated_by")
            .order_by("display_order", "created_at")
        )
        if search:
            qs = qs.filter(product__name__icontains=search)
        if visibility:
            qs = qs.filter(visibility=visibility)
        total = qs.count()
        offset = (page - 1) * page_size
        items = list(qs[offset : offset + page_size])
        return {"count": total, "results": items}

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_profile(*, product_id: str, actor, data: dict[str, Any]) -> ProductShowcaseProfile:
        from apps.product_registry.models import Product

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            raise ShowcaseServiceError(f"Product '{product_id}' not found.")

        if ProductShowcaseProfile.objects.filter(product_id=product_id).exists():
            raise ShowcaseServiceError("A showcase profile already exists for this product.")

        display_order = data.get("display_order", 0)
        if not isinstance(display_order, int) or display_order < 0:
            raise ShowcaseServiceError("display_order must be a non-negative integer.")

        profile = ProductShowcaseProfile.objects.create(
            product=product,
            tagline=data.get("tagline", ""),
            overview=data.get("overview", ""),
            visibility=data.get("visibility", ShowcaseVisibility.DRAFT),
            display_order=display_order,
            created_by=actor,
            updated_by=actor,
        )
        return profile

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def update_profile(*, profile_id: str, actor, data: dict[str, Any]) -> ProductShowcaseProfile:
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        if "visibility" in data and data["visibility"] not in ShowcaseVisibility.values:
            raise ShowcaseServiceError(
                f"Invalid visibility '{data['visibility']}'. Allowed: {ShowcaseVisibility.values}"
            )

        display_order = data.get("display_order")
        if display_order is not None:
            if not isinstance(display_order, int) or display_order < 0:
                raise ShowcaseServiceError("display_order must be a non-negative integer.")
            profile.display_order = display_order

        for field in ("tagline", "overview"):
            if field in data:
                setattr(profile, field, data[field])

        if "visibility" in data:
            profile.visibility = data["visibility"]

        profile.updated_by = actor
        profile.save()
        return profile

    # ------------------------------------------------------------------
    # Publish / unpublish
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def publish_profile(*, profile_id: str, actor) -> ProductShowcaseProfile:
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        previous = profile.visibility
        profile.visibility = ShowcaseVisibility.PUBLISHED
        profile.updated_by = actor
        profile.save()

        record_audit_event(
            action=AuditAction.SHOWCASE_PROFILE_PUBLISHED,
            target_type=AuditTargetType.SHOWCASE_PROFILE,
            target_id=str(profile.id),
            target_repr=f"ShowcaseProfile({profile.product.name})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=None,
            metadata={
                "product_code": profile.product.code,
                "product_name": profile.product.name,
                "profile_id": str(profile.id),
                "previous_visibility": previous,
                "resulting_visibility": ShowcaseVisibility.PUBLISHED,
            },
        )
        return profile

    @staticmethod
    @transaction.atomic
    def unpublish_profile(*, profile_id: str, actor) -> ProductShowcaseProfile:
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        previous = profile.visibility
        profile.visibility = ShowcaseVisibility.HIDDEN
        profile.updated_by = actor
        profile.save()

        record_audit_event(
            action=AuditAction.SHOWCASE_PROFILE_UNPUBLISHED,
            target_type=AuditTargetType.SHOWCASE_PROFILE,
            target_id=str(profile.id),
            target_repr=f"ShowcaseProfile({profile.product.name})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=None,
            metadata={
                "product_code": profile.product.code,
                "product_name": profile.product.name,
                "profile_id": str(profile.id),
                "previous_visibility": previous,
                "resulting_visibility": ShowcaseVisibility.HIDDEN,
            },
        )
        return profile

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def reorder_profiles(*, ordered_ids: list[str], actor) -> None:
        """Assign sequential display_order values to the given profile IDs."""
        for idx, pid in enumerate(ordered_ids):
            updated = ProductShowcaseProfile.objects.filter(pk=pid).update(
                display_order=idx, updated_by=actor
            )
            if updated == 0:
                raise ShowcaseServiceError(f"Showcase profile '{pid}' not found.")

    # ------------------------------------------------------------------
    # Media management
    # ------------------------------------------------------------------
    @staticmethod
    def add_media(*, profile_id: str, actor, data: dict[str, Any]) -> ProductShowcaseMedia:
        try:
            profile = ProductShowcaseProfile.objects.get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        url = data.get("url", "")
        _check_url(url, "url")

        return ProductShowcaseMedia.objects.create(
            profile=profile,
            media_type=data["media_type"],
            title=data.get("title", ""),
            url=url,
            display_order=data.get("display_order", 0),
            created_by=actor,
        )

    @staticmethod
    def delete_media(*, media_id: str) -> None:
        deleted, _ = ProductShowcaseMedia.objects.filter(pk=media_id).delete()
        if deleted == 0:
            raise ShowcaseServiceError(f"Showcase media '{media_id}' not found.")

    # ------------------------------------------------------------------
    # Launchability contract & Demo Launch
    # ------------------------------------------------------------------
    @staticmethod
    def launchability_contract(*, profile_id: str) -> dict[str, Any]:
        """Returns launchability contract derived from ProductLaunchConfig, demo environment, and SSO configuration."""
        from apps.assignments.constants import AccessState
        from apps.assignments.models import AssignmentStatus, UserProductAssignment
        from apps.assignments.services.effective_access import compute_user_tenant_effective_access
        from apps.identity.models import PlatformUser
        from apps.integration_hub.models import ConnectorInstance, InstanceStatus, ProductSsoClient
        from apps.organizations.models import Organization

        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        launch_config = (
            ProductLaunchConfig.objects.filter(
                models.Q(profile=profile) | models.Q(product=profile.product)
            )
            .select_related("target_environment")
            .first()
        )

        if launch_config is None:
            return {
                "launchable": False,
                "reason": "LAUNCH_CONFIG_NOT_FOUND",
                "launch_mode": None,
                "allowed_targets": [],
            }

        if launch_config.launch_mode == ProductLaunchConfig.LaunchMode.DISABLED:
            return {
                "launchable": False,
                "reason": "LAUNCH_DISABLED",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        target_env = launch_config.target_environment
        if not target_env or not target_env.is_active:
            return {
                "launchable": False,
                "reason": "DEMO_ENVIRONMENT_INACTIVE",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        sso_client = ProductSsoClient.objects.filter(product=profile.product, is_active=True).first()
        if not sso_client:
            return {
                "launchable": False,
                "reason": "SSO_CLIENT_NOT_CONFIGURED",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        policy = launch_config.policy or {}
        demo_org_id = policy.get("demo_organization_id")
        demo_org_code = policy.get("demo_organization_code")
        org_q = models.Q(id=demo_org_id) if demo_org_id else models.Q(code=demo_org_code)
        demo_org = Organization.objects.filter(org_q).first() if (demo_org_id or demo_org_code) else None

        if not demo_org:
            return {
                "launchable": False,
                "reason": "DEMO_ORGANIZATION_MISSING",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        if demo_org.code not in AUTHORIZED_DEMO_ORGANIZATION_CODES:
            return {
                "launchable": False,
                "reason": "DEMO_CONTEXT_NOT_PERMITTED",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        instance = ConnectorInstance.objects.filter(
            connector__product=profile.product,
            organization=demo_org,
            status=InstanceStatus.ACTIVE,
        ).first()
        if not instance:
            return {
                "launchable": False,
                "reason": "INTEGRATION_INSTANCE_MISSING",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        demo_user_id = policy.get("demo_user_id")
        demo_user_email = policy.get("demo_user_email")
        user_q = models.Q(id=demo_user_id) if demo_user_id else models.Q(email=demo_user_email)
        demo_user = PlatformUser.objects.filter(user_q).first() if (demo_user_id or demo_user_email) else None

        if not demo_user:
            return {
                "launchable": False,
                "reason": "DEMO_USER_MISSING",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        from apps.organizations.models import MembershipStatus, OrganizationMembership
        membership = OrganizationMembership.objects.filter(
            organization=demo_org,
            user=demo_user,
            status=MembershipStatus.ACTIVE,
        ).first()
        if not membership:
            return {
                "launchable": False,
                "reason": "DEMO_MEMBERSHIP_INACTIVE",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        assignment = UserProductAssignment.objects.filter(
            user=demo_user,
            organization=demo_org,
            product=profile.product,
            status=AssignmentStatus.ACTIVE,
        ).first()
        if not assignment:
            return {
                "launchable": False,
                "reason": "DEMO_ASSIGNMENT_INACTIVE",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        effective = compute_user_tenant_effective_access(demo_user, demo_org)
        entitled_prod_ids = {
            p.get("id")
            for p in effective.get("entitled_products", [])
            if p.get("access_state") == AccessState.AVAILABLE or p.get("is_entitled")
        }
        if str(profile.product_id) not in entitled_prod_ids:
            return {
                "launchable": False,
                "reason": "DEMO_ACCESS_DENIED",
                "launch_mode": launch_config.launch_mode,
                "allowed_targets": launch_config.allowed_targets,
            }

        return {
            "launchable": True,
            "reason": "READY",
            "launch_mode": launch_config.launch_mode,
            "allowed_targets": launch_config.allowed_targets,
            "environment_name": target_env.name,
            "demo_user": demo_user.email,
            "demo_organization": demo_org.code,
            "target_environment": {
                "id": str(target_env.id),
                "name": target_env.name,
                "base_url": target_env.base_url,
            },
            "demo_context": {
                "organization_code": demo_org.code,
                "organization_name": demo_org.name,
                "user_email": demo_user.email,
            },
        }

    @staticmethod
    def launch_demo(*, profile_id: str, actor) -> dict[str, Any]:
        """Initiates an authorized live demo SSO launch for a showcase profile."""
        from apps.identity.models import PlatformUser
        from apps.integration_hub.sso_service import issue_sso_authorization_code
        from apps.organizations.models import Organization

        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        contract = ProductShowcaseService.launchability_contract(profile_id=profile_id)
        if not contract.get("launchable"):
            raise ShowcaseServiceError(f"Cannot launch demo: {contract.get('reason')}")

        launch_config = ProductLaunchConfig.objects.filter(
            models.Q(profile=profile) | models.Q(product=profile.product)
        ).select_related("target_environment").first()

        policy = launch_config.policy or {}
        demo_org_id = policy.get("demo_organization_id")
        demo_org_code = policy.get("demo_organization_code")
        org_q = models.Q(id=demo_org_id) if demo_org_id else models.Q(code=demo_org_code)
        demo_org = Organization.objects.get(org_q)

        demo_user_id = policy.get("demo_user_id")
        demo_user_email = policy.get("demo_user_email")
        user_q = models.Q(id=demo_user_id) if demo_user_id else models.Q(email=demo_user_email)
        demo_user = PlatformUser.objects.get(user_q)

        sso_result = issue_sso_authorization_code(
            user=demo_user,
            organization=demo_org,
            product=profile.product,
        )

        record_audit_event(
            action=AuditAction.SHOWCASE_DEMO_LAUNCHED,
            target_type=AuditTargetType.SHOWCASE_PROFILE,
            target_id=str(profile.id),
            target_repr=f"ShowcaseProfile({profile.product.name})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=None,
            metadata={
                "operation": "showcase_demo_launched",
                "product_code": profile.product.code,
                "profile_id": str(profile.id),
                "product_name": profile.product.name,
                "demo_user": demo_user.email,
                "demo_organization": demo_org.code,
                "demo_environment_id": str(launch_config.target_environment_id) if launch_config.target_environment_id else None,
                "demo_environment_name": launch_config.target_environment.name if launch_config.target_environment else None,
            },
        )

        expires_at_val = sso_result.get("expires_at")
        expires_at_str = expires_at_val.isoformat() if hasattr(expires_at_val, "isoformat") else str(expires_at_val)

        return {
            "redirect_url": sso_result["redirect_url"],
            "expires_at": expires_at_str,
            "demo_user": demo_user.email,
            "demo_organization": demo_org.code,
            "product_name": profile.product.name,
            "target_name": launch_config.target_environment.name if launch_config.target_environment else "",
        }

    @staticmethod
    @transaction.atomic
    def configure_launch(*, profile_id: str, actor, data: dict[str, Any]) -> ProductLaunchConfig:
        """Configures or updates ProductLaunchConfig for a showcase profile."""
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            raise ShowcaseServiceError(f"Showcase profile '{profile_id}' not found.")

        launch_config = ProductLaunchConfig.objects.filter(
            models.Q(profile=profile) | models.Q(product=profile.product)
        ).first()

        if not launch_config:
            launch_config = ProductLaunchConfig(
                product=profile.product,
                profile=profile,
                created_by=actor,
                updated_by=actor,
            )

        if "launch_mode" in data:
            if data["launch_mode"] not in ProductLaunchConfig.LaunchMode.values:
                raise ShowcaseServiceError(f"Invalid launch_mode '{data['launch_mode']}'.")
            launch_config.launch_mode = data["launch_mode"]

        if "target_environment_id" in data:
            env_id = data["target_environment_id"]
            if env_id:
                try:
                    env = ProductDemoEnvironment.objects.get(pk=env_id, product=profile.product)
                    launch_config.target_environment = env
                except ProductDemoEnvironment.DoesNotExist:
                    raise ShowcaseServiceError(f"Demo environment '{env_id}' not found.")
            else:
                launch_config.target_environment = None

        if "allowed_targets" in data:
            launch_config.allowed_targets = data["allowed_targets"]

        if "policy" in data:
            policy_data = data["policy"]
            if isinstance(policy_data, dict):
                org_code = policy_data.get("demo_organization_code")
                if org_code and org_code not in AUTHORIZED_DEMO_ORGANIZATION_CODES:
                    raise ShowcaseServiceError(
                        f"Organization '{org_code}' is not an authorized Showcase demo context."
                    )
            launch_config.policy = policy_data

        if "notes" in data:
            launch_config.notes = data["notes"]

        launch_config.updated_by = actor
        launch_config.save()

        record_audit_event(
            action=AuditAction.SHOWCASE_CONFIG_CHANGED,
            target_type=AuditTargetType.SHOWCASE_PROFILE,
            target_id=str(profile.id),
            target_repr=f"ShowcaseProfile({profile.product.name})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=None,
            metadata={
                "product_code": profile.product.code,
                "profile_id": str(profile.id),
                "product_name": profile.product.name,
                "launch_mode": launch_config.launch_mode,
                "target_environment_id": str(launch_config.target_environment_id) if launch_config.target_environment_id else None,
            },
        )

        return launch_config



class DemoEnvironmentService:
    """CRUD for ProductDemoEnvironment allowlisted records."""

    @staticmethod
    def list_environments(*, product_id: str) -> list[ProductDemoEnvironment]:
        return list(
            ProductDemoEnvironment.objects.filter(product_id=product_id).select_related("product")
        )

    @staticmethod
    @transaction.atomic
    def create_environment(*, product_id: str, actor, data: dict[str, Any]) -> ProductDemoEnvironment:
        from apps.product_registry.models import Product

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            raise ShowcaseServiceError(f"Product '{product_id}' not found.")

        base_url = data.get("base_url", "")
        _check_url(base_url, "base_url")

        return ProductDemoEnvironment.objects.create(
            product=product,
            name=data["name"],
            base_url=base_url,
            description=data.get("description", ""),
            is_active=data.get("is_active", True),
            created_by=actor,
            updated_by=actor,
        )

    @staticmethod
    @transaction.atomic
    def update_environment(*, env_id: str, actor, data: dict[str, Any]) -> ProductDemoEnvironment:
        try:
            env = ProductDemoEnvironment.objects.get(pk=env_id)
        except ProductDemoEnvironment.DoesNotExist:
            raise ShowcaseServiceError(f"Demo environment '{env_id}' not found.")

        if "base_url" in data:
            _check_url(data["base_url"], "base_url")
            env.base_url = data["base_url"]

        for field in ("name", "description", "is_active"):
            if field in data:
                setattr(env, field, data[field])

        env.updated_by = actor
        env.save()
        return env

    @staticmethod
    def delete_environment(*, env_id: str) -> None:
        deleted, _ = ProductDemoEnvironment.objects.filter(pk=env_id).delete()
        if deleted == 0:
            raise ShowcaseServiceError(f"Demo environment '{env_id}' not found.")


class ShowcasePresentationService:
    """Read-only presentation-mode data — no owner controls, no tenant data."""

    @staticmethod
    def presentation_portfolio(
        *, category_filter: str | None = None
    ) -> list[ProductShowcaseProfile]:
        """Return published profiles ordered by display_order for presentation mode."""
        qs = (
            ProductShowcaseProfile.objects.filter(visibility=ShowcaseVisibility.PUBLISHED)
            .select_related("product")
            .prefetch_related("media")
            .order_by("display_order", "created_at")
        )
        if category_filter:
            qs = qs.filter(product__name__icontains=category_filter)
        return list(qs)
