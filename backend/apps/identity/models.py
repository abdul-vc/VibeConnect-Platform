"""Identity Domain Models.

Defines the custom PlatformUser model and manager for VibeConnect master platform,
supporting central user lifecycle transitions, login attempt tracking,
and PostgreSQL-backed constraints.
"""

import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class UserStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DISABLED = "disabled", "Disabled"


class PlatformUserManager(BaseUserManager):
    """Custom manager for PlatformUser enforcing case-insensitive email normalization."""

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        """Normalize the full email address by stripping whitespace and converting to lowercase."""
        if not email:
            return ""
        return email.strip().lower()

    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "PlatformUser":
        """Create and return a regular platform user."""
        if not email:
            raise ValueError("The Email field is mandatory.")

        normalized_email = self.normalize_email(email)
        if not normalized_email:
            raise ValueError("A valid non-empty email address is required.")

        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_platform_owner", False)

        # Stage 1 compatibility: auto-sync status if not explicitly passed
        if "status" not in extra_fields:
            if extra_fields.get("is_active") is False:
                extra_fields["status"] = UserStatus.DISABLED
            else:
                extra_fields["status"] = UserStatus.ACTIVE
        else:
            extra_fields["is_active"] = (extra_fields["status"] == UserStatus.ACTIVE)

        user = self.model(email=normalized_email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields) -> "PlatformUser":
        """Create and return a superuser with full administrative privileges."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_platform_owner", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("status", UserStatus.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("is_platform_owner") is not True:
            raise ValueError("Superuser must have is_platform_owner=True.")
        if extra_fields.get("is_active") is not True:
            raise ValueError("Superuser must have is_active=True.")
        if not password:
            raise ValueError("Superuser must have a valid password.")

        return self.create_user(email, password, **extra_fields)


class PlatformUser(AbstractBaseUser, PermissionsMixin):
    """VibeConnect custom user model.

    Supports multi-tenant platform ownership, federation identity tracking,
    lifecycle state transitions, and case-insensitive email identities.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier for the platform user.",
    )
    email = models.EmailField(
        unique=True,
        db_index=True,
        max_length=255,
        verbose_name="Email Address",
        help_text="Case-insensitive unique email identity.",
    )
    full_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Full Name",
    )
    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        db_index=True,
        verbose_name="Lifecycle Status",
        help_text="Lifecycle state of the platform user account.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active Status",
        help_text="Designates whether this user account is active.",
    )
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Email Verified At",
        help_text="Timestamp when the user email identity was verified.",
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name="Staff Status",
        help_text="Designates whether the user can log into the Django admin.",
    )
    is_platform_owner = models.BooleanField(
        default=False,
        verbose_name="Platform Owner Status",
        help_text="Designates whether the user possesses root platform ownership privileges.",
    )
    auth_provider = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Authentication Provider",
        help_text="Optional identifier of the identity provider (e.g. local, saml, oidc).",
    )
    external_subject_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="External Subject ID",
        help_text="Optional subject claim/ID from an external identity provider.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At",
    )

    objects = PlatformUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "platform_users"
        verbose_name = "Platform User"
        verbose_name_plural = "Platform Users"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="unique_platform_user_email_case_insensitive",
            ),
            models.CheckConstraint(
                condition=Q(status__in=UserStatus.values),
                name="platform_user_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status=UserStatus.ACTIVE) & Q(is_active=True))
                    | (Q(status__in=[UserStatus.SUSPENDED, UserStatus.DISABLED]) & Q(is_active=False))
                ),
                name="platform_user_status_is_active_sync",
            ),
        ]

    def clean(self):
        """Ensure email is consistently normalized on model validation."""
        super().clean()
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        """Ensure email normalization, check transition validity against persisted state, and auto-sync status/is_active."""
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)

        persisted = None
        if self.pk:
            persisted = (
                PlatformUser.objects.filter(pk=self.pk)
                .values("status", "is_active")
                .first()
            )

        update_fields = kwargs.get("update_fields")
        fields_set = set(update_fields) if update_fields is not None else None

        # 1. Enforce Terminal Disabled Status against persisted database state
        if persisted and persisted["status"] == UserStatus.DISABLED:
            attempting_status = (fields_set is None or "status" in fields_set) and (self.status != UserStatus.DISABLED)
            attempting_active = (fields_set is None or "is_active" in fields_set) and (self.is_active is True)
            if attempting_status or attempting_active:
                raise ValidationError(
                    "Disabled user cannot be reactivated; status is terminal in Phase 2D.",
                    code="USER_DISABLED_TERMINAL",
                )

        # 2. Field-level resolution & transition enforcement
        if not persisted:
            # New instance: status takes priority if it was explicitly provided.
            if self.status and self.status != UserStatus.ACTIVE:
                # status is explicitly non-active (suspended/disabled) — trust it
                self.is_active = False
            elif not self.is_active and self.status == UserStatus.ACTIVE:
                # Legacy is_active=False with default status: infer disabled
                self.status = UserStatus.DISABLED
            elif self.status:
                self.is_active = (self.status == UserStatus.ACTIVE)
            else:
                self.status = UserStatus.ACTIVE
                self.is_active = True
        elif fields_set is not None:
            if "is_active" in fields_set and "status" not in fields_set:
                # Legacy is_active save: user.save(update_fields=["is_active"])
                if not self.is_active:
                    # If suspended, preserve suspended; if active, transition to disabled
                    if persisted["status"] == UserStatus.SUSPENDED:
                        self.status = UserStatus.SUSPENDED
                    else:
                        self.status = UserStatus.DISABLED
                else:
                    # If suspended, transition to active
                    self.status = UserStatus.ACTIVE
                fields_set.add("status")
                kwargs["update_fields"] = list(fields_set)

            elif "status" in fields_set and "is_active" not in fields_set:
                # Status-only save: user.save(update_fields=["status"])
                self.is_active = (self.status == UserStatus.ACTIVE)
                fields_set.add("is_active")
                kwargs["update_fields"] = list(fields_set)

            elif "status" in fields_set and "is_active" in fields_set:
                # Both specified: ensure consistency
                expected_active = (self.status == UserStatus.ACTIVE)
                if self.is_active != expected_active:
                    self.is_active = expected_active
        else:
            # Full save without update_fields
            if self.status != persisted["status"]:
                self.is_active = (self.status == UserStatus.ACTIVE)
            elif self.is_active != persisted["is_active"]:
                if not self.is_active:
                    self.status = (
                        UserStatus.SUSPENDED
                        if persisted["status"] == UserStatus.SUSPENDED
                        else UserStatus.DISABLED
                    )
                else:
                    self.status = UserStatus.ACTIVE
            else:
                self.is_active = (self.status == UserStatus.ACTIVE)

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email


class LoginAttempt(models.Model):
    """Immutable evidence store for authentication attempts.

    Records successful and failed login attempts with keyed HMAC hashes
    of identifier and IP address to isolate unauthenticated flood traffic
    from the append-only AuditLog.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts",
    )
    identifier_hash = models.CharField(
        max_length=128,
        db_index=True,
    )
    result = models.CharField(
        max_length=20,
        choices=[("success", "Success"), ("failure", "Failure")],
    )
    failure_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
    )
    ip_hash = models.CharField(
        max_length=128,
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        db_table = "login_attempts"
        verbose_name = "Login Attempt"
        verbose_name_plural = "Login Attempts"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["identifier_hash", "-occurred_at"], name="login_attempt_ident_idx"),
            models.Index(fields=["ip_hash", "-occurred_at"], name="login_attempt_ip_idx"),
        ]

    def __str__(self) -> str:
        return f"LoginAttempt({self.result}, {self.failure_code} at {self.occurred_at})"


class ImpersonationSessionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    TERMINATED = "terminated", "Terminated"
    REVOKED = "revoked", "Revoked"


def compute_default_impersonation_expiry():
    """Default server-computed expiry timestamp enforcing the strict 30-minute hard cap."""
    return timezone.now() + timezone.timedelta(minutes=30)


class SupportImpersonationSession(models.Model):
    """Time-limited, auditable impersonation session for Support Operators.

    Locked Governance Rules:
    - Target user must be an active Tenant Admin or Member in target_organization.
    - Platform Owners and other Support Operators are never valid targets (enforced at model/service layer).
    - Hard cap of 30 minutes from creation, server-computed, never client-supplied.
    - Silent extension is strictly forbidden: expires_at cannot be pushed once created.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operated_impersonation_sessions",
        verbose_name="Operator",
        help_text="Support operator executing the session.",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="targeted_impersonation_sessions",
        verbose_name="Target User",
        help_text="Tenant Admin or Member user being impersonated.",
    )
    target_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="impersonation_sessions",
        verbose_name="Target Organization",
        help_text="Organization scope of the impersonation session.",
    )
    reason = models.CharField(
        max_length=500,
        verbose_name="Reason",
        help_text="Mandatory operational justification (1-500 trimmed characters).",
    )
    ticket_reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Ticket Reference",
        help_text="Optional external ticketing or incident reference identifier.",
    )
    status = models.CharField(
        max_length=20,
        choices=ImpersonationSessionStatus.choices,
        default=ImpersonationSessionStatus.ACTIVE,
        db_index=True,
        verbose_name="Session Status",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )
    expires_at = models.DateTimeField(
        default=compute_default_impersonation_expiry,
        db_index=True,
        verbose_name="Expires At",
        help_text="Server-computed hard cap timestamp (maximum 30 minutes from creation).",
    )
    terminated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Terminated At",
    )
    correlation_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name="Correlation ID",
    )

    class Meta:
        db_table = "support_impersonation_sessions"
        verbose_name = "Support Impersonation Session"
        verbose_name_plural = "Support Impersonation Sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["operator", "status"], name="impers_operator_status_idx"),
            models.Index(fields=["target_organization", "status"], name="impers_org_status_idx"),
            models.Index(fields=["status", "expires_at"], name="impers_status_expiry_idx"),
        ]

    def clean(self):
        super().clean()
        now = timezone.now()

        # 1. Reason validation (1-500 trimmed characters)
        clean_reason = (self.reason or "").strip()
        if not clean_reason:
            raise ValidationError("Reason is required and cannot be empty.", code="REASON_REQUIRED")
        if len(clean_reason) > 500:
            raise ValidationError("Reason cannot exceed 500 characters.", code="REASON_TOO_LONG")
        self.reason = clean_reason

        # 1b. Ticket Reference validation (1-100 trimmed characters, mandatory)
        clean_ticket = (self.ticket_reference or "").strip()
        if not clean_ticket:
            raise ValidationError("Ticket reference is required and cannot be empty.", code="TICKET_REFERENCE_REQUIRED")
        if len(clean_ticket) > 100:
            raise ValidationError("Ticket reference cannot exceed 100 characters.", code="TICKET_REFERENCE_TOO_LONG")
        self.ticket_reference = clean_ticket

        # 2. Server-computed 30-minute cap & No silent extension
        max_duration = timezone.timedelta(minutes=30)
        is_new_instance = (getattr(self, "_state", None) is not None and self._state.adding) or not self.pk

        persisted = None
        if not is_new_instance and self.pk:
            persisted = SupportImpersonationSession.objects.filter(pk=self.pk).values("expires_at", "status").first()
            if persisted is None:
                is_new_instance = True

        if is_new_instance:
            if not self.expires_at:
                self.expires_at = now + max_duration
            elif self.expires_at > now + max_duration:
                raise ValidationError("Initial session duration cannot exceed 30 minutes.", code="DURATION_EXCEEDED")
            elif self.expires_at <= now:
                raise ValidationError("Initial session expiry must be in the future.", code="EXPIRY_IN_PAST")
        else:
            if persisted and self.expires_at > persisted["expires_at"]:
                raise ValidationError("Silent session extension is prohibited. Start a new session instead.", code="EXTENSION_PROHIBITED")


        # 3. Target eligibility validation
        if self.target_user_id:
            if self.operator_id and str(self.operator_id) == str(self.target_user_id):
                raise ValidationError("Operator cannot target their own account for impersonation.", code="SELF_IMPERSONATION_REJECTED")

            # Platform Owners and Superusers are never valid targets
            if getattr(self.target_user, "is_platform_owner", False) or getattr(self.target_user, "is_superuser", False):
                raise ValidationError("Platform Owners cannot be targeted for impersonation.", code="TARGET_INELIGIBLE_PLATFORM_OWNER")

            # Support Operators (users with platform role assignments) are never valid targets
            from apps.access_control.models import PlatformRoleAssignment
            if PlatformRoleAssignment.objects.filter(user_id=self.target_user_id).exists():
                raise ValidationError("Support Operators cannot be targeted for impersonation.", code="TARGET_INELIGIBLE_SUPPORT_OPERATOR")

            # Must be active user
            if getattr(self.target_user, "status", None) != "active" or not getattr(self.target_user, "is_active", False):
                raise ValidationError("Target user must be active.", code="TARGET_USER_NOT_ACTIVE")

            # Must have active Tenant Admin or Member membership in target_organization
            from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
            target_membership = OrganizationMembership.objects.filter(
                user_id=self.target_user_id,
                organization_id=self.target_organization_id,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not target_membership:
                raise ValidationError("Target user must hold an active membership in the target organization.", code="TARGET_NO_MEMBERSHIP")
            if target_membership.membership_type not in (MembershipType.TENANT_ADMIN, MembershipType.MEMBER):
                raise ValidationError("Target user must be an active Tenant Admin or Member.", code="TARGET_INVALID_MEMBERSHIP_TYPE")

    def save(self, *args, **kwargs):
        self.clean()
        # Auto-expire if past expiry timestamp
        if self.status == ImpersonationSessionStatus.ACTIVE and self.expires_at and timezone.now() >= self.expires_at:
            self.status = ImpersonationSessionStatus.EXPIRED
            if not self.terminated_at:
                self.terminated_at = self.expires_at
        super().save(*args, **kwargs)

    def is_currently_active(self) -> bool:
        """Evaluate whether this session is currently active and within time bounds."""
        if self.status != ImpersonationSessionStatus.ACTIVE:
            return False
        if timezone.now() >= self.expires_at:
            self.status = ImpersonationSessionStatus.EXPIRED
            if not self.terminated_at:
                self.terminated_at = self.expires_at
            self.save(update_fields=["status", "terminated_at"])
            return False
        return True

    def __str__(self) -> str:
        return f"SupportImpersonationSession({self.operator} -> {self.target_user} [{self.status}])"

