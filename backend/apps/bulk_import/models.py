"""Bulk Import Domain Models (Phase 3D).

Supports staged validation, idempotent enqueue, row-level progress tracking,
and asynchronous commit separation for bulk user and membership imports.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization


class BulkImportType(models.TextChoices):
    USERS_AND_MEMBERSHIPS = "users_and_memberships", "Users and Memberships"


class BulkImportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    VALIDATING = "validating", "Validating"
    VALIDATED = "validated", "Validated"
    COMMITTING = "committing", "Committing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class RowValidationState(models.TextChoices):
    PENDING = "pending", "Pending"
    VALID = "valid", "Valid"
    INVALID = "invalid", "Invalid"
    COMMITTED = "committed", "Committed"
    FAILED = "failed", "Failed"


class BulkImportJob(models.Model):
    """Tracks a bulk data import job with staged validation and commit separation."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bulk_import_jobs",
    )
    import_type = models.CharField(
        max_length=50,
        choices=BulkImportType.choices,
        default=BulkImportType.USERS_AND_MEMBERSHIPS,
    )
    status = models.CharField(
        max_length=20,
        choices=BulkImportStatus.choices,
        default=BulkImportStatus.PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Client-supplied or content-derived key to prevent duplicate job processing.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bulk_import_jobs",
    )
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    committed_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bulk_import_jobs"
        verbose_name = "Bulk Import Job"
        verbose_name_plural = "Bulk Import Jobs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Import Job {self.id} [{self.status}] ({self.committed_rows}/{self.total_rows})"


class BulkImportRow(models.Model):
    """Individual staged row within a bulk import job."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    job = models.ForeignKey(
        BulkImportJob,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_number = models.PositiveIntegerField()
    validation_state = models.CharField(
        max_length=20,
        choices=RowValidationState.choices,
        default=RowValidationState.PENDING,
        db_index=True,
    )
    payload_ref = models.JSONField(
        default=dict,
        help_text="Staged row parameters (e.g. email, full_name, role_code). No secrets.",
    )
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    error_message = models.TextField(
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bulk_import_rows"
        verbose_name = "Bulk Import Row"
        verbose_name_plural = "Bulk Import Rows"
        ordering = ["job", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "row_number"],
                name="uniq_row_number_per_job",
            ),
        ]

    def __str__(self) -> str:
        return f"Job {self.job_id} Row {self.row_number} [{self.validation_state}]"
