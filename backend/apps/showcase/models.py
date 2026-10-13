"""Product Showcase & Demo Hub Models – Phase 11.

Four models only, reconciled against apps.product_registry.Product.
No product data is duplicated; all product references are FK to Product.

Visibility enum: draft / published / hidden
URL allowlist: https-only, no javascript:/data: schemes enforced at the service layer.
"""

import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


ALLOWED_DEMO_URL_SCHEMES = re.compile(r"^https://", re.IGNORECASE)
BLOCKED_URL_SCHEMES = re.compile(r"^(javascript:|data:|http://)", re.IGNORECASE)


def validate_demo_url(value: str) -> None:
    """Reject dangerous schemes and non-https unless local development environment."""
    if not value:
        return
    lower_val = value.lower()
    if lower_val.startswith("javascript:") or lower_val.startswith("data:"):
        raise ValidationError(
            "Demo URLs must use HTTPS. javascript: and data: schemes are rejected."
        )

    # In local/demo development environments, allow localhost / 127.0.0.1 HTTP URLs
    is_local_env = getattr(settings, "DEBUG", False) or getattr(settings, "ENVIRONMENT", "") in (
        "development",
        "local",
        "demo",
        "test",
    )
    if is_local_env:
        import urllib.parse
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1"):
            return

    if not ALLOWED_DEMO_URL_SCHEMES.match(value):
        raise ValidationError("Demo URLs must begin with https://.")



class ShowcaseVisibility(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    HIDDEN = "hidden", "Hidden"


class ProductShowcaseProfile(models.Model):
    """Owner-managed showcase presentation layer for a registered Product.

    One profile per product (UniqueConstraint). Visibility drives presentation
    mode — only 'published' profiles appear in the public portfolio.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="showcase_profile",
    )
    tagline = models.CharField(max_length=200, blank=True, default="")
    overview = models.TextField(blank=True, default="")
    visibility = models.CharField(
        max_length=20,
        choices=ShowcaseVisibility.choices,
        default=ShowcaseVisibility.DRAFT,
    )
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_showcase_profiles",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_showcase_profiles",
    )

    class Meta:
        db_table = "showcase_profiles"
        verbose_name = "Product Showcase Profile"
        verbose_name_plural = "Product Showcase Profiles"
        ordering = ["display_order", "created_at"]

    def __str__(self) -> str:
        return f"ShowcaseProfile({self.product_id}, {self.visibility})"


class ProductShowcaseMedia(models.Model):
    """Ordered media attachments for a ProductShowcaseProfile."""

    class MediaType(models.TextChoices):
        SCREENSHOT = "screenshot", "Screenshot"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        ProductShowcaseProfile,
        on_delete=models.CASCADE,
        related_name="media",
    )
    media_type = models.CharField(max_length=20, choices=MediaType.choices)
    title = models.CharField(max_length=150)
    url = models.URLField(max_length=2048, validators=[validate_demo_url])
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_showcase_media",
    )

    class Meta:
        db_table = "showcase_media"
        verbose_name = "Showcase Media"
        verbose_name_plural = "Showcase Media"
        ordering = ["display_order", "created_at"]

    def __str__(self) -> str:
        return f"ShowcaseMedia({self.title}, {self.media_type})"


class ProductDemoEnvironment(models.Model):
    """Allowlisted demo environment metadata record for a product.

    Only records stored here can ever be referenced as demo targets.
    Free-text URLs are never accepted at launch time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="demo_environments",
    )
    name = models.CharField(max_length=100)
    base_url = models.URLField(max_length=2048, validators=[validate_demo_url])
    description = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_demo_environments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_demo_environments",
    )

    class Meta:
        db_table = "showcase_demo_environments"
        verbose_name = "Demo Environment"
        verbose_name_plural = "Demo Environments"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"DemoEnvironment({self.name}, {self.product_id})"


class ProductLaunchConfig(models.Model):
    """Launch configuration bound to a Product with allowlisted demo targets.

    'launchable' is always False in Phase 11 (SSO_NOT_CONFIGURED).
    """

    class LaunchMode(models.TextChoices):
        DISABLED = "disabled", "Disabled"
        DEMO_ONLY = "demo_only", "Demo Only"
        SSO_DIRECT = "sso_direct", "SSO Direct"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(
        "product_registry.Product",
        on_delete=models.CASCADE,
        related_name="launch_config",
        null=True,
        blank=True,
    )
    profile = models.OneToOneField(
        ProductShowcaseProfile,
        on_delete=models.CASCADE,
        related_name="launch_config",
        null=True,
        blank=True,
    )
    launch_mode = models.CharField(
        max_length=30,
        choices=LaunchMode.choices,
        default=LaunchMode.DISABLED,
    )
    allowed_targets = models.JSONField(default=list, blank=True)
    policy = models.JSONField(default=dict, blank=True)
    target_environment = models.ForeignKey(
        ProductDemoEnvironment,
        on_delete=models.PROTECT,
        related_name="launch_configs",
        null=True,
        blank=True,
    )
    notes = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_launch_configs",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_launch_configs",
    )

    class Meta:
        db_table = "showcase_launch_configs"
        verbose_name = "Product Launch Config"
        verbose_name_plural = "Product Launch Configs"

    def __str__(self) -> str:
        return f"LaunchConfig(profile={self.profile_id})"
