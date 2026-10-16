"""Access Control Domain Models (Phase 2E Stage 1).

Defines the master identity and access control plane models:
- ConsoleModule: Platform Owner and Tenant Admin console workspaces.
- AccessPermission: Canonical control-plane permissions mapped to console modules.
- Role: System-defined and organization-scoped administrative roles.
- RolePermission: Granular role-to-permission mappings.
- OrganizationConsoleModulePolicy: Organization-level console module maximum ceilings.
- OrganizationPermissionCeiling: Organization-level permission maximum ceilings.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class ConsoleModuleContext(models.TextChoices):
    PLATFORM_OWNER = "platform_owner", "Platform Owner"
    TENANT = "tenant", "Tenant"
    SUPPORT = "support", "Support"


class RoleStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class ConsoleModule(models.Model):
    """Console module representing administrative workspaces in the control plane."""

    key = models.CharField(
        max_length=100,
        primary_key=True,
        help_text="Canonical unique identifier for the console module.",
    )
    display_name = models.CharField(
        max_length=150,
        help_text="Human-readable title of the console module.",
    )
    description = models.TextField(
        blank=True,
        help_text="Functional description of the module.",
    )
    target_context = models.CharField(
        max_length=50,
        choices=ConsoleModuleContext.choices,
        help_text="Target console context (platform_owner or tenant).",
    )
    is_core = models.BooleanField(
        default=False,
        help_text="True if this module is essential and cannot be disabled.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Global administrative lifecycle status of the module.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering for navigation.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "console_modules"
        ordering = ["sort_order", "key"]
        constraints = [
            models.CheckConstraint(
                condition=Q(target_context__in=ConsoleModuleContext.values),
                name="console_module_valid_context",
            ),
            models.CheckConstraint(
                condition=~Q(is_core=True, is_active=False),
                name="core_module_cannot_be_inactive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.key})"


class AccessPermission(models.Model):
    """Canonical fine-grained control-plane permission definition."""

    key = models.CharField(
        max_length=100,
        primary_key=True,
        help_text="Dot-separated permission key (e.g. roles.view).",
    )
    console_module = models.ForeignKey(
        ConsoleModule,
        on_delete=models.PROTECT,
        related_name="permissions",
        db_index=True,
        help_text="Console module governing this permission.",
    )
    display_name = models.CharField(
        max_length=150,
        help_text="Human-readable display name.",
    )
    description = models.TextField(
        blank=True,
        help_text="Functional description of capability granted.",
    )
    category = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Logical grouping category (e.g. roles).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="System-wide active status.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "access_permissions"
        ordering = ["sort_order", "key"]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.key})"


class Role(models.Model):
    """Administrative role within the VibeConnect control plane.

    Can be system-defined (is_system_role=True, organization=None) or
    organization-scoped (is_system_role=False, organization!=None).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier for the role.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="roles",
        help_text="Owning organization for custom roles. Null for system roles.",
    )
    code = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Immutable lowercase alphanumeric code with single underscores.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Editable display name for the role.",
    )
    description = models.TextField(
        blank=True,
        help_text="Functional summary of role duties.",
    )
    is_system_role = models.BooleanField(
        default=False,
        help_text="True if this is an immutable platform-defined system role.",
    )
    status = models.CharField(
        max_length=20,
        choices=RoleStatus.choices,
        default=RoleStatus.ACTIVE,
        help_text="Lifecycle state (active or retired).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Platform user who created this custom role.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Platform user who last updated this custom role.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_roles"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
                name="role_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=RoleStatus.values),
                name="role_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(is_system_role=True) & Q(organization__isnull=True))
                    | (Q(is_system_role=False) & Q(organization__isnull=False))
                ),
                name="role_system_or_custom_org_scope",
            ),
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_custom_role_code_per_org",
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(is_system_role=True),
                name="unique_system_role_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.code}]"


class RolePermission(models.Model):
    """Associates an AccessPermission with a Role."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
        help_text="Role receiving the permission.",
    )
    permission = models.ForeignKey(
        AccessPermission,
        on_delete=models.PROTECT,
        related_name="role_permissions",
        help_text="Permission granted to the role.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="unique_role_permission",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role.code} -> {self.permission.key}"


class OrganizationConsoleModulePolicy(models.Model):
    """Organization-level maximum console module ceiling configured by Platform Owner."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="console_module_policies",
        help_text="Organization subject to this module policy.",
    )
    console_module = models.ForeignKey(
        ConsoleModule,
        on_delete=models.PROTECT,
        related_name="organization_policies",
        help_text="Target console module.",
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text="True if module is enabled for this organization.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Platform Owner who last modified this ceiling.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_console_module_policies"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "console_module"],
                name="unique_org_console_module_policy",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization.code} : {self.console_module.key} = {self.is_enabled}"


class OrganizationPermissionCeiling(models.Model):
    """Organization-level maximum permission ceiling configured by Platform Owner."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="permission_ceilings",
        help_text="Organization subject to this permission ceiling.",
    )
    permission = models.ForeignKey(
        AccessPermission,
        on_delete=models.PROTECT,
        related_name="organization_ceilings",
        help_text="Target control-plane permission.",
    )
    is_allowed = models.BooleanField(
        default=False,
        help_text="True if permission is permitted for this organization.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Platform Owner who last modified this ceiling.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_permission_ceilings"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "permission"],
                name="unique_org_permission_ceiling",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization.code} : {self.permission.key} = {self.is_allowed}"


class PlatformRoleAssignment(models.Model):
    """Associates a platform-scoped Role with a PlatformUser.

    Enables platform-level role assignment (e.g. Support Operator)
    without requiring an Organization or tenant membership.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_role_assignments",
        help_text="Platform user assigned this role.",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="platform_assignments",
        help_text="Platform-level role granted to the user.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_role_assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                name="unique_platform_user_role",
            ),
        ]

    def clean(self):
        super().clean()
        if hasattr(self, "role") and self.role:
            if not self.role.is_system_role or self.role.organization is not None:
                from django.core.exceptions import ValidationError
                raise ValidationError(
                    "Only system-defined platform roles without an organization can be assigned.",
                    code="PLATFORM_ROLE_INVALID",
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user} -> {self.role.code}"

