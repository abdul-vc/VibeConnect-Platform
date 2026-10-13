"""Onboarding Domain Models (Phase 3B).

Implements TenantOnboardingCase:
- Step-driven state machine tracking partial progress.
- Resumable workflow preserving wizard state across sessions.
- Final step provisions Organization, initial Admin invitation, and commercial plan.
"""

import uuid
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

CODE_REGEX = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
code_validator = RegexValidator(
    regex=CODE_REGEX,
    message="Code must be lowercase alphanumeric with single hyphens or underscores.",
)


class OnboardingStep(models.TextChoices):
    ORGANIZATION_PROFILE = "organization_profile", "Organization Profile"
    ADMIN_SETUP = "admin_setup", "Admin Setup"
    PLAN_SELECTION = "plan_selection", "Plan Selection"
    REVIEW_CONFIRM = "review_confirm", "Review & Confirm"
    COMPLETED = "completed", "Completed"


class OnboardingCaseStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"
    PROVISIONING_FAILED = "provisioning_failed", "Provisioning Failed"


VALID_STEP_TRANSITIONS: dict[str, set[str]] = {
    OnboardingStep.ORGANIZATION_PROFILE: {
        OnboardingStep.ORGANIZATION_PROFILE,
        OnboardingStep.ADMIN_SETUP,
    },
    OnboardingStep.ADMIN_SETUP: {
        OnboardingStep.ORGANIZATION_PROFILE,
        OnboardingStep.ADMIN_SETUP,
        OnboardingStep.PLAN_SELECTION,
    },
    OnboardingStep.PLAN_SELECTION: {
        OnboardingStep.ADMIN_SETUP,
        OnboardingStep.PLAN_SELECTION,
        OnboardingStep.REVIEW_CONFIRM,
    },
    OnboardingStep.REVIEW_CONFIRM: {
        OnboardingStep.PLAN_SELECTION,
        OnboardingStep.REVIEW_CONFIRM,
        OnboardingStep.COMPLETED,
    },
    OnboardingStep.COMPLETED: set(),
}


class TenantOnboardingCase(models.Model):
    """Resumable, audited tenant onboarding workflow entity.

    Persists partial progress across wizard steps without prematurely
    creating orphaned database entities.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    status = models.CharField(
        max_length=20,
        choices=OnboardingCaseStatus.choices,
        default=OnboardingCaseStatus.IN_PROGRESS,
        db_index=True,
        help_text="Overall status of the onboarding case.",
    )
    current_step = models.CharField(
        max_length=32,
        choices=OnboardingStep.choices,
        default=OnboardingStep.ORGANIZATION_PROFILE,
        db_index=True,
        help_text="Current active step in the onboarding sequence.",
    )
    # Organization Profile draft parameters
    organization_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Requested lowercase code for the new organization.",
    )
    organization_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Requested human-readable name of the organization.",
    )
    organization_description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Optional description for the organization.",
    )
    # Admin details draft parameters
    admin_email = models.EmailField(
        max_length=255,
        blank=True,
        default="",
        help_text="Email of the prospective tenant administrator.",
    )
    admin_full_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Full name of the prospective tenant administrator.",
    )
    # Plan selection parameters
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="onboarding_cases",
        help_text="Selected commercial plan version.",
    )
    plan_price = models.ForeignKey(
        "plans.PlanPrice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="onboarding_cases",
        help_text="Selected pricing interval and currency.",
    )
    is_trial = models.BooleanField(
        default=True,
        help_text="Whether to initialize as a 14-day trial subscription.",
    )
    # Provisioned organization reference
    created_organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="onboarding_cases",
        help_text="Created Organization record upon completion.",
    )
    # Audit and lifecycle actors
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_onboarding_cases",
        help_text="Platform Owner who initiated the case.",
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when onboarding case was opened.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when all steps were executed and provisioned.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of latest step modification.",
    )

    class Meta:
        db_table = "tenant_onboarding_cases"
        ordering = ["-started_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=OnboardingCaseStatus.values),
                name="valid_onboarding_case_status",
            ),
            models.CheckConstraint(
                condition=Q(current_step__in=OnboardingStep.values),
                name="valid_onboarding_current_step",
            ),
        ]

    def __str__(self) -> str:
        return f"Case {self.id} [{self.organization_code or 'unnamed'}] ({self.status}: {self.current_step})"
