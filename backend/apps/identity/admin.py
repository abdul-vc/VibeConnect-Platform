# pyright: reportIncompatibleVariableOverride=false
# pyright: reportMissingTypeStubs=false
"""Identity admin configuration.

PlatformUserAdmin enforces the last-active-owner rule in a locked transaction
inside save_model() and propagates any validation failure back to the admin
changeform as a user-visible error (not an HTTP 500).
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.identity.constants import SYSTEM_SERVICE_ACTOR_EMAIL
from .models import LoginAttempt, PlatformUser


class PlatformUserAdminForm(forms.ModelForm):
    """Admin form that validates last-active-owner constraints before saving."""

    class Meta:
        model = PlatformUser
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if not cleaned:
            return cleaned

        instance = self.instance

        if not instance.pk:
            return cleaned

        # Fetch persisted state from DB — never trust form.initial for security decisions
        persisted = (
            PlatformUser.objects.filter(pk=instance.pk)
            .values("is_platform_owner", "status", "is_active")
            .first()
        )
        if not persisted:
            return cleaned

        was_active_owner = (
            persisted["is_platform_owner"] and persisted["status"] == "active"
        )
        if not was_active_owner:
            return cleaned

        new_is_owner = cleaned.get("is_platform_owner", persisted["is_platform_owner"])
        new_status = cleaned.get("status", persisted["status"])

        deactivating_owner = (not new_is_owner) or (new_status != "active")
        if not deactivating_owner:
            return cleaned

        # Count remaining active human owners (this user and system service actor excluded)
        active_owner_count = (
            PlatformUser.objects.filter(is_platform_owner=True, status="active")
            .exclude(pk=instance.pk)
            .exclude(email=SYSTEM_SERVICE_ACTOR_EMAIL)
            .count()
        )

        if active_owner_count == 0:
            raise ValidationError(
                "Cannot deactivate or revoke privileges from the final active Platform Owner."
            )

        return cleaned


@admin.register(PlatformUser)
class PlatformUserAdmin(admin.ModelAdmin):
    form = PlatformUserAdminForm
    list_display = (
        "email",
        "full_name",
        "status",
        "is_active",
        "is_staff",
        "is_platform_owner",
        "created_at",
    )
    search_fields = ("email", "full_name", "external_subject_id")
    list_filter = ("status", "is_active", "is_staff", "is_platform_owner", "auth_provider")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "email_verified_at")

    def save_model(self, request, obj, form, change):
        """Save PlatformUser inside a locked atomic transaction.

        Acquires row-level locks on active platform owners, re-checks
        persisted state to prevent TOCTOU races, then performs the save
        inside the same transaction.  Validation failures are surfaced as
        admin messages rather than propagated as HTTP 500 responses.
        """
        try:
            with transaction.atomic():  # type: ignore[attr-defined]
                if change and obj.pk:
                    # Acquire row locks on all active qualifying human owners
                    active_owners = list(
                        PlatformUser.objects.select_for_update()
                        .filter(is_platform_owner=True, status="active")
                        .exclude(email=SYSTEM_SERVICE_ACTOR_EMAIL)
                        .order_by("id")
                    )

                    # Re-read persisted state inside the locked transaction
                    persisted_owner = (
                        PlatformUser.objects.filter(pk=obj.pk)
                        .values("is_platform_owner", "status")
                        .first()
                    )

                    if persisted_owner and (
                        persisted_owner["is_platform_owner"]
                        and persisted_owner["status"] == "active"
                        and obj.email != SYSTEM_SERVICE_ACTOR_EMAIL
                    ):
                        # Is the edit deactivating or revoking ownership?
                        deactivating = (not obj.is_platform_owner) or (
                            obj.status != "active"
                        )
                        if deactivating and len(active_owners) <= 1:
                            raise ValidationError(
                                "Cannot deactivate the final active Platform Owner "
                                "under concurrent edit."
                            )

                # Ensure plain text password entered via Django admin is hashed
                raw_password = form.cleaned_data.get("password") if form else None
                if raw_password and not raw_password.startswith(("pbkdf2_sha256$", "argon2$", "bcrypt$")):
                    obj.set_password(raw_password)

                super().save_model(request, obj, form, change)

        except ValidationError as exc:
            messages.error(request, exc.message)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            messages.error(request, exc.message)
            opts = self.model._meta
            return HttpResponseRedirect(
                reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_change",
                    args=[object_id],
                )
            )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("result", "failure_code", "identifier_hash", "ip_hash", "occurred_at")
    list_filter = ("result", "failure_code")
    search_fields = ("identifier_hash", "ip_hash")
    ordering = ("-occurred_at",)
    readonly_fields = (
        "id", "user", "identifier_hash", "result", "failure_code",
        "ip_hash", "occurred_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
