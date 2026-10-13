"""Branding Domain Models (Phase 4A/4B).

Provides models for:
- BrandingProfile: Scoped to an organization (tenant) or null (global system default).
- BrandAsset: Uploaded branding assets (logo, favicon, banner) with type/size validation and SVG safety.
- BrandingRevision: Versioned branding state with strict application-level and DB-level immutability for published revisions.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# Allowlisted CSS custom property token keys and their strict format validators
ALLOWLISTED_BRANDING_TOKENS = {
    "brand_primary": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "brand_primary_hover": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "brand_primary_light": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "brand_gradient": re.compile(r"^(linear-gradient\(.+\)|#[0-9a-fA-F]{3,8})$"),
    "bg_app": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "text_primary": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "text_secondary": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
    "border_focus": re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,\s\.\%]+\))$"),
}

DEFAULT_GLOBAL_TOKENS = {
    "brand_primary": "#6366f1",
    "brand_primary_hover": "#4f46e5",
    "brand_primary_light": "rgba(99, 102, 241, 0.16)",
    "brand_gradient": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #38bdf8 100%)",
    "bg_app": "#070b14",
    "text_primary": "#f8fafc",
    "text_secondary": "#94a3b8",
    "border_focus": "#6366f1",
}

UNSAFE_SVG_PATTERNS = [
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onload, onclick, onerror, etc.
    re.compile(r"<iframe[\s>]", re.IGNORECASE),
    re.compile(r"<object[\s>]", re.IGNORECASE),
    re.compile(r"<embed[\s>]", re.IGNORECASE),
]


def validate_tokens_dict(tokens: Any) -> dict[str, str]:
    """Validate that tokens is a dict with only allowlisted keys and valid color formats."""
    if not isinstance(tokens, dict):
        raise ValidationError({"tokens": "Tokens must be a JSON object dictionary."})

    cleaned: dict[str, str] = {}
    for key, val in tokens.items():
        if key not in ALLOWLISTED_BRANDING_TOKENS:
            raise ValidationError({"tokens": f"Disallowed token key '{key}'. Allowed keys: {list(ALLOWLISTED_BRANDING_TOKENS.keys())}"})
        if not isinstance(val, str) or not ALLOWLISTED_BRANDING_TOKENS[key].match(val.strip()):
            raise ValidationError({"tokens": f"Invalid format for token '{key}': '{val}'."})
        cleaned[key] = val.strip()

    return cleaned


def validate_svg_content(content: str) -> None:
    """Check SVG file content for embedded script tags or active event handlers."""
    for pattern in UNSAFE_SVG_PATTERNS:
        if pattern.search(content):
            raise ValidationError("SVG contains unsafe script or event handler elements.")


class BrandingProfile(models.Model):
    """Branding profile representing either global platform branding or tenant-specific override."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="branding_profile",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "branding_profiles"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                name="unique_organization_branding_profile",
                condition=models.Q(organization__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        if self.organization:
            return f"Tenant Branding: {self.organization.name}"
        return "Global Branding Profile (Default)"

    @property
    def is_global(self) -> bool:
        return self.organization is None


class BrandAsset(models.Model):
    """Uploaded branding asset (logo, favicon, banner) with size and safety checks."""

    ASSET_TYPES = [
        ("logo", "Logo"),
        ("favicon", "Favicon"),
        ("banner", "Banner"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        BrandingProfile,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    asset_type = models.CharField(max_length=30, choices=ASSET_TYPES)
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()  # in bytes
    file_data = models.TextField()  # Base64 encoded or data URL
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "branding_assets"
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.file_size > 2 * 1024 * 1024:
            raise ValidationError({"file_size": "Asset file size cannot exceed 2MB."})

        allowed_types = ["image/png", "image/jpeg", "image/svg+xml", "image/webp", "image/x-icon"]
        if self.content_type not in allowed_types:
            raise ValidationError({"content_type": f"Unsupported asset content type '{self.content_type}'. Allowed: {allowed_types}"})

        if self.content_type == "image/svg+xml" or self.file_name.lower().endswith(".svg"):
            validate_svg_content(self.file_data)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.get_asset_type_display()}: {self.file_name} ({self.profile.name})"


class BrandingRevision(models.Model):
    """Immutable published or editable draft branding revision for a profile."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        BrandingProfile,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    revision_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    tokens = models.JSONField(default=dict)
    logo_asset = models.ForeignKey(
        BrandAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    favicon_asset = models.ForeignKey(
        BrandAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "branding_revisions"
        ordering = ["-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "revision_number"],
                name="unique_profile_revision_number",
            ),
            models.UniqueConstraint(
                fields=["profile"],
                condition=models.Q(status="published"),
                name="unique_published_revision_per_profile",
            ),
        ]

    def clean(self):
        super().clean()
        if self.tokens:
            validate_tokens_dict(self.tokens)

        # Single DB-level/model guard for immutability
        if self.pk:
            orig = (
                BrandingRevision.objects.filter(pk=self.pk)
                .values("status", "tokens", "logo_asset_id", "favicon_asset_id")
                .first()
            )
            if orig and orig["status"] == "published":
                if (
                    orig["tokens"] != self.tokens
                    or orig["status"] != self.status
                    or orig["logo_asset_id"] != self.logo_asset_id
                    or orig["favicon_asset_id"] != self.favicon_asset_id
                ):
                    raise ValidationError("Published revisions are immutable.")

    def save(self, *args, **kwargs):
        if self.pk:
            orig = (
                BrandingRevision.objects.filter(pk=self.pk)
                .values("status", "tokens", "logo_asset_id", "favicon_asset_id")
                .first()
            )
            if orig and orig["status"] == "published":
                if (
                    orig["tokens"] != self.tokens
                    or orig["status"] != self.status
                    or orig["logo_asset_id"] != self.logo_asset_id
                    or orig["favicon_asset_id"] != self.favicon_asset_id
                ):
                    raise ValidationError("Published revisions are immutable.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.profile.name} - Rev #{self.revision_number} ({self.status})"
