"""Branding Domain Services (Phase 4A/4B).

Handles:
- Active branding resolution with tenant-to-global fallback
- Draft creation & updates with allowlisted token schema validation
- Atomic publish with row lock (select_for_update)
- Rollback creating a new revision copy
- Safe asset upload with type, size, and SVG safety verification
"""

from __future__ import annotations

import base64
from typing import Any
import uuid

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.branding.models import (
    ALLOWLISTED_BRANDING_TOKENS,
    DEFAULT_GLOBAL_TOKENS,
    BrandAsset,
    BrandingProfile,
    BrandingRevision,
    validate_tokens_dict,
)
from apps.organizations.models import Organization


class BrandingServiceError(Exception):
    """Domain exception raised by branding service operations."""
    def __init__(self, message: str, code: str = "BRANDING_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


def get_active_branding(organization_id: uuid.UUID | str | None = None) -> dict[str, Any]:
    """Resolve active published branding for an organization, falling back to global default.

    Edge Case 2: Tenant with no override falls back to global default.
    """
    clean_org_id = None
    if organization_id:
        try:
            clean_org_id = uuid.UUID(str(organization_id))
        except (ValueError, TypeError):
            clean_org_id = None

    # 1. Try finding tenant-specific active profile & published revision
    if clean_org_id:
        tenant_profile = BrandingProfile.objects.filter(
            organization_id=clean_org_id,
            is_active=True,
        ).first()

        if tenant_profile:
            published_rev = tenant_profile.revisions.filter(status="published").first()
            if published_rev:
                merged_tokens = dict(DEFAULT_GLOBAL_TOKENS)
                merged_tokens.update(published_rev.tokens or {})
                return {
                    "profile_id": str(tenant_profile.id),
                    "profile_name": tenant_profile.name,
                    "organization_id": str(clean_org_id),
                    "is_override": True,
                    "is_global_fallback": False,
                    "revision_id": str(published_rev.id),
                    "revision_number": published_rev.revision_number,
                    "published_at": published_rev.published_at.isoformat() if published_rev.published_at else None,
                    "tokens": merged_tokens,
                    "logo_asset": _serialize_asset_simple(published_rev.logo_asset),
                    "favicon_asset": _serialize_asset_simple(published_rev.favicon_asset),
                }

    # 2. Fall back to Global Platform Profile
    global_profile = BrandingProfile.objects.filter(
        organization__isnull=True,
        is_active=True,
    ).first()

    if global_profile:
        published_rev = global_profile.revisions.filter(status="published").first()
        if published_rev:
            merged_tokens = dict(DEFAULT_GLOBAL_TOKENS)
            merged_tokens.update(published_rev.tokens or {})
            return {
                "profile_id": str(global_profile.id),
                "profile_name": global_profile.name,
                "organization_id": None,
                "is_override": False,
                "is_global_fallback": True,
                "revision_id": str(published_rev.id),
                "revision_number": published_rev.revision_number,
                "published_at": published_rev.published_at.isoformat() if published_rev.published_at else None,
                "tokens": merged_tokens,
                "logo_asset": _serialize_asset_simple(published_rev.logo_asset),
                "favicon_asset": _serialize_asset_simple(published_rev.favicon_asset),
            }

    # 3. Default fallback if no profile exists yet
    return {
        "profile_id": None,
        "profile_name": "Default Theme",
        "organization_id": None,
        "is_override": False,
        "is_global_fallback": True,
        "revision_id": None,
        "revision_number": 0,
        "published_at": None,
        "tokens": dict(DEFAULT_GLOBAL_TOKENS),
        "logo_asset": None,
        "favicon_asset": None,
    }


def get_or_create_profile(
    *,
    organization: Organization | None = None,
    actor: Any = None,
    name: str | None = None,
) -> BrandingProfile:
    """Retrieve or initialize a branding profile."""
    if organization:
        profile = BrandingProfile.objects.filter(organization=organization).first()
        if not profile:
            profile = BrandingProfile.objects.create(
                organization=organization,
                name=name or f"{organization.name} Branding",
                created_by=actor,
                updated_by=actor,
            )
            # Create initial draft revision with default tokens
            BrandingRevision.objects.create(
                profile=profile,
                revision_number=1,
                status="draft",
                tokens=dict(DEFAULT_GLOBAL_TOKENS),
                created_by=actor,
            )
        return profile
    else:
        profile = BrandingProfile.objects.filter(organization__isnull=True).first()
        if not profile:
            profile = BrandingProfile.objects.create(
                organization=None,
                name=name or "Global Default Branding",
                created_by=actor,
                updated_by=actor,
            )
            # Initialize with published revision for the global default
            now = timezone.now()
            BrandingRevision.objects.create(
                profile=profile,
                revision_number=1,
                status="published",
                tokens=dict(DEFAULT_GLOBAL_TOKENS),
                published_at=now,
                published_by=actor,
                created_by=actor,
            )
        return profile


def create_draft_revision(
    *,
    profile_id: uuid.UUID | str,
    actor: Any,
    tokens: dict[str, str] | None = None,
    logo_asset_id: uuid.UUID | str | None = None,
    favicon_asset_id: uuid.UUID | str | None = None,
) -> BrandingRevision:
    """Create a new draft revision for a profile."""
    profile = BrandingProfile.objects.get(id=profile_id)

    # Next revision number
    max_rev = profile.revisions.aggregate(models.Max("revision_number"))["revision_number__max"] or 0
    next_rev = max_rev + 1

    clean_tokens = validate_tokens_dict(tokens) if tokens is not None else dict(DEFAULT_GLOBAL_TOKENS)

    logo_asset = None
    if logo_asset_id:
        logo_asset = BrandAsset.objects.get(id=logo_asset_id, profile=profile)

    favicon_asset = None
    if favicon_asset_id:
        favicon_asset = BrandAsset.objects.get(id=favicon_asset_id, profile=profile)

    revision = BrandingRevision.objects.create(
        profile=profile,
        revision_number=next_rev,
        status="draft",
        tokens=clean_tokens,
        logo_asset=logo_asset,
        favicon_asset=favicon_asset,
        created_by=actor,
    )
    return revision


def update_draft_revision(
    *,
    revision_id: uuid.UUID | str,
    actor: Any,
    tokens: dict[str, str] | None = None,
    logo_asset_id: uuid.UUID | str | None = None,
    favicon_asset_id: uuid.UUID | str | None = None,
) -> BrandingRevision:
    """Update an existing draft revision. Rejects updates if revision is published."""
    revision = BrandingRevision.objects.get(id=revision_id)

    if revision.status == "published":
        raise BrandingServiceError("Published revisions are immutable.", code="REVISION_IMMUTABLE")

    if tokens is not None:
        clean_tokens = validate_tokens_dict(tokens)
        revision.tokens = clean_tokens

    if logo_asset_id is not None:
        revision.logo_asset = BrandAsset.objects.get(id=logo_asset_id, profile=revision.profile) if logo_asset_id else None

    if favicon_asset_id is not None:
        revision.favicon_asset = BrandAsset.objects.get(id=favicon_asset_id, profile=revision.profile) if favicon_asset_id else None

    revision.save()
    return revision


def publish_revision(
    *,
    revision_id: uuid.UUID | str,
    actor: Any,
) -> BrandingRevision:
    """Publish a revision with row lock (select_for_update) to prevent race conditions.

    Edge Case 3: Concurrent publish handled via row lock.
    Validation Rule: Exactly one published revision per profile.
    """
    with transaction.atomic():
        try:
            revision = BrandingRevision.objects.select_for_update().get(id=revision_id)
        except BrandingRevision.DoesNotExist:
            raise BrandingServiceError("Revision not found.", code="NOT_FOUND")

        profile = BrandingProfile.objects.select_for_update().get(id=revision.profile_id)

        # Edge Case 1: Invalid config on publish
        if not revision.tokens:
            raise BrandingServiceError("Cannot publish empty token configuration.", code="INVALID_CONFIG")
        validate_tokens_dict(revision.tokens)

        # Archive any currently published revisions for this profile
        profile.revisions.filter(status="published").exclude(id=revision.id).update(status="archived")

        now = timezone.now()
        revision.status = "published"
        revision.published_at = now
        revision.published_by = actor
        revision.save()

        # Audit log publish
        _record_branding_audit(
            action="branding_revision_published",
            target=revision,
            actor=actor,
            organization_id=profile.organization_id,
            metadata={
                "profile_id": str(profile.id),
                "profile_name": profile.name,
                "revision_number": revision.revision_number,
                "is_global": profile.is_global,
            },
        )

        return revision


def rollback_to_revision(
    *,
    target_revision_id: uuid.UUID | str,
    actor: Any,
) -> BrandingRevision:
    """Roll back to a prior revision by copying its tokens/assets into a NEW published revision.

    Requirements: Rollback creates a new revision copy, preserving auditability.
    Edge Case 4: Rollback target already superseded handled naturally via new revision copy.
    """
    with transaction.atomic():
        try:
            target = BrandingRevision.objects.select_for_update().get(id=target_revision_id)
        except BrandingRevision.DoesNotExist:
            raise BrandingServiceError("Target revision for rollback not found.", code="NOT_FOUND")

        profile = BrandingProfile.objects.select_for_update().get(id=target.profile_id)

        max_rev = profile.revisions.aggregate(models.Max("revision_number"))["revision_number__max"] or 0
        new_rev_number = max_rev + 1

        # Archive any existing published revisions for this profile
        profile.revisions.filter(status="published").update(status="archived")

        now = timezone.now()
        new_revision = BrandingRevision.objects.create(
            profile=profile,
            revision_number=new_rev_number,
            status="published",
            tokens=dict(target.tokens or {}),
            logo_asset=target.logo_asset,
            favicon_asset=target.favicon_asset,
            published_at=now,
            published_by=actor,
            created_by=actor,
        )

        # Audit log rollback
        _record_branding_audit(
            action="branding_revision_rolled_back",
            target=new_revision,
            actor=actor,
            organization_id=profile.organization_id,
            metadata={
                "profile_id": str(profile.id),
                "target_revision_id": str(target.id),
                "target_revision_number": target.revision_number,
                "new_revision_number": new_rev_number,
                "is_global": profile.is_global,
            },
        )

        return new_revision


def upload_brand_asset(
    *,
    profile_id: uuid.UUID | str,
    actor: Any,
    asset_type: str,
    file_name: str,
    content_type: str,
    file_bytes: bytes,
) -> BrandAsset:
    """Upload and validate a brand asset (logo/favicon/banner) with size, type, and SVG checks."""
    profile = BrandingProfile.objects.get(id=profile_id)

    # Basic size check
    file_size = len(file_bytes)
    if file_size > 2 * 1024 * 1024:
        raise BrandingServiceError("Asset file size exceeds 2MB limit.", code="FILE_TOO_LARGE")

    # Encode data as Base64 data URL
    b64_str = base64.b64encode(file_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64_str}"

    asset = BrandAsset(
        profile=profile,
        asset_type=asset_type,
        file_name=file_name,
        content_type=content_type,
        file_size=file_size,
        file_data=data_url,
        created_by=actor,
    )
    # Triggers full_clean() including SVG sanitization check
    try:
        asset.full_clean()
    except ValidationError as err:
        raise BrandingServiceError(str(err), code="INVALID_ASSET")

    asset.save()
    return asset


def _serialize_asset_simple(asset: BrandAsset | None) -> dict[str, Any] | None:
    if not asset:
        return None
    return {
        "id": str(asset.id),
        "asset_type": asset.asset_type,
        "file_name": asset.file_name,
        "content_type": asset.content_type,
        "file_size": asset.file_size,
        "file_data": asset.file_data,
    }


def _record_branding_audit(
    *,
    action: str,
    target: Any,
    actor: Any,
    organization_id: uuid.UUID | None,
    metadata: dict[str, Any],
) -> None:
    """Safely log branding events using existing AuditLog models."""
    try:
        with transaction.atomic():
            if organization_id:
                AuditLog.objects.create(
                    action=AuditAction.ORGANIZATION_UPDATED,
                    target_type=AuditTargetType.ORGANIZATION,
                    target_id=organization_id,
                    target_repr=f"Branding(Rev #{getattr(target, 'revision_number', 0)})",
                    actor=actor,
                    actor_email=getattr(actor, "email", "system"),
                    actor_name=getattr(actor, "full_name", ""),
                    organization_id=organization_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={"event": action, **metadata},
                )
            else:
                AuditLog.objects.create(
                    action=AuditAction.SHOWCASE_CONFIG_CHANGED,
                    target_type=AuditTargetType.SHOWCASE_PROFILE,
                    target_id=target.id,
                    target_repr=f"GlobalBranding(Rev #{getattr(target, 'revision_number', 0)})",
                    actor=actor,
                    actor_email=getattr(actor, "email", "system"),
                    actor_name=getattr(actor, "full_name", ""),
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={"event": action, **metadata},
                )
    except Exception:
        # Audit failure must not crash business transaction
        pass
