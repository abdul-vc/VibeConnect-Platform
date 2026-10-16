# VibeConnect — Data Inventory and Privacy Retention Policy (Phase 6F-1)

**Status:** PROPOSED, NOT APPROVED (No legal, regulatory, or business authority has ratified these retention periods)  
**Scope:** Master Control Plane (`PlatformUser`, `AuditLog`, `UsageEvent`, `UsageBucket`, `DeveloperApiKey`, `DeveloperWebhookDelivery`, `IntegrationEvent`, `ProvisioningJob`, `IntegrationFailure`, `IntegrationReconciliationIssue`, `SupportImpersonationSession`)

---

## 1. Executive Summary

This document establishes the comprehensive inventory of personal, sensitive, and operational data persisted across the VibeConnect SaaS platform. It documents each data model's business purpose, direct and indirect personal identifiers, foreign key dependency constraints, current retention behavior, and proposed retention windows.

Critically, this document isolates and analyzes the core architectural tension between **AuditLog Immutability** and **Personal Data Erasure Requests (Right to be Forgotten / Anonymization)**.

---

## 2. Comprehensive Model Inventory

| Model | Business Purpose | Personal Data Fields Present | FK Dependencies & Constraints | Current Retention | Proposed Retention Window (PROPOSED, NOT APPROVED) |
|---|---|---|---|---|---|
| **PlatformUser** (`apps/identity/models.py:88-160`) | Central identity for platform authentication, RBAC, and ownership | `email`, `full_name`, `auth_provider`, `external_subject_id` | Referenced by `AuditLog.actor` (`PROTECT`), `OrganizationMembership.user` (`PROTECT`), `DeveloperApplication.created_by` (`PROTECT`), `SupportImpersonationSession.operator/target_user` (`PROTECT`) | Indefinite (active lifecycle) | Indefinite while active; Anonymization / pseudonymization upon account termination |
| **AuditLog** (`apps/auditlog/models.py:210-280`) | Forensic, immutable audit trail for security and governance | `actor_email`, `actor_name`, IP/actor metadata, snapshot details | `actor` (`models.PROTECT` -> `PlatformUser`). `AuditLogQuerySet` prohibits `delete()` and `update()`. | Indefinite (append-only) | 7 Years for compliance/forensic records (PROPOSED, NOT APPROVED) |
| **UsageEvent** (`apps/usage_metering/models.py:26-69`) | Raw ingestion telemetry for metered quotas | None directly (org-scoped, `event_key`, `quantity`). May contain tenant identifiers in metadata | `organization` (`CASCADE`), `meter` (`PROTECT`), `product` (`PROTECT`) | Indefinite | 90 Days post-billing cycle aggregation (PROPOSED, NOT APPROVED) |
| **UsageBucket** (`apps/usage_metering/models.py:70-106`) | Aggregated periodic consumption counters | None (aggregated count per org/meter/period) | `organization` (`CASCADE`), `meter` (`PROTECT`) | Indefinite | 3 Years for commercial billing auditability (PROPOSED, NOT APPROVED) |
| **DeveloperApiKey** (`apps/developer_console/models.py:47-103`) | API authentication for tenant/platform developers | Key metadata only (`name`, `key_prefix`, `hashed_secret`). No plaintext secret or PII | `application` (`CASCADE`). `application.created_by` (`PROTECT` -> `PlatformUser`) | Indefinite | Revoked/expired keys archived after 1 Year (PROPOSED, NOT APPROVED) |
| **DeveloperWebhookDelivery** (`apps/developer_console/models.py:155-192`) | Outbound webhook delivery tracking and payload inspection | `payload` JSON (may contain user emails, names, or invitation tokens depending on event topic), `response_body` | `subscription` (`CASCADE`) | Indefinite | 30 Days post-delivery (PROPOSED, NOT APPROVED) |
| **IntegrationEvent** (`apps/integration_hub/models.py:180-230`) | Inbound/outbound connector event logs | `payload` JSON (may contain student/instructor LMS identifiers, emails) | `instance` (`CASCADE`) | Indefinite | 60 Days post-processing (PROPOSED, NOT APPROVED) |
| **ProvisioningJob** (`apps/integration_hub/models.py:231-310`) | Asynchronous LMS provisioning job execution queue | `payload` JSON, `result_summary` | `instance` (`CASCADE`) | Indefinite | 90 Days post-completion (PROPOSED, NOT APPROVED) |
| **IntegrationFailure** (`apps/integration_hub/models.py:311-370`) | Dead-letter and transient failure diagnostic logs | `error_details` JSON, payload excerpts | `instance` (`CASCADE`) | Indefinite | 180 Days post-resolution (PROPOSED, NOT APPROVED) |
| **IntegrationReconciliationIssue** (`apps/integration_hub/models.py:650-710`) | Discrepancy tracking between VibeConnect and external LMS | `issue_details` JSON | `instance` (`CASCADE`) | Indefinite | 1 Year post-resolution (PROPOSED, NOT APPROVED) |
| **SupportImpersonationSession** (`apps/identity/models.py:365-436`) | Audited, time-limited operator impersonation sessions | `reason` (may reference incident tickets or individual complaints), `operator_id`, `target_user_id` | `operator` (`PROTECT`), `target_user` (`PROTECT`), `target_organization` (`PROTECT`) | Indefinite | 3 Years for support audit compliance (PROPOSED, NOT APPROVED) |

---

## 3. CRITICAL SECTION: The AuditLog Immutability vs. Personal Data Erasure Conflict

### A. The Structural Conflict
Under privacy frameworks (such as GDPR Article 17 "Right to Erasure" and CCPA/CPRA):
1. Data subjects possess the legal right to request erasure of their personal identifiers (e.g. `email`, `full_name`).
2. Conversely, VibeConnect's regulatory, security, and forensic integrity requires an **immutable, append-only AuditLog** (`apps/auditlog/models.py:187-198`). The application strictly prohibits ORM updates and deletions:
   ```python
   class AuditLogQuerySet(models.QuerySet):
       def update(self, **kwargs):
           raise AuditLogImmutableError("Audit records are immutable and cannot be updated.")
       def delete(self):
           raise AuditLogImmutableError("Audit records are append-only and cannot be deleted.")
   ```
3. Furthermore, the `actor` field on `AuditLog` enforces `on_delete=models.PROTECT` ([models.py:230](file:///c:/VibeConnect-Platform/backend/apps/auditlog/models.py#L230)). Any attempt to execute `PlatformUser.objects.get(...).delete()` triggers a `django.db.models.ProtectedError`, mechanically blocking deletion.

### B. Resolution Architecture: Pseudonymization at Source vs. Historical Immutability
To resolve this without corrupting forensic history:
1. **Never mutate or delete historical `AuditLog` rows**: Historical events (`actor_email`, `actor_name`, `timestamp`, `action`) represent immutable historical facts of actions executed at that historical moment.
2. **Implement Live Pseudonymization on `PlatformUser` (`6F-2`)**:
   - De-identify directly-identifying attributes on the live `PlatformUser` record:
     - `email` -> replaced with deterministic/pseudonymous tombstone: `anonymized-<uuid>@redacted.vibeconnect.local`
     - `full_name` -> `"Redacted User"`
     - `is_active` -> `False`
     - `status` -> `UserStatus.DISABLED`
     - `password` -> set to unusable
     - `auth_provider` & `external_subject_id` -> cleared (`None`)
   - The user's primary key (`id` UUID) is retained to preserve referential integrity across `on_delete=models.PROTECT` foreign keys.
3. **Explicit Disclosure of Persistence**:
   - The system **must not falsely claim** that PII was erased from historical audit logs if historical snapshots persist.
   - Formal privacy disclosure documents that historical audit rows retain historical event snapshots strictly for legal compliance and security audit purposes under statutory exemptions (e.g., GDPR Art. 17(3)(b) compliance with a legal obligation).

---

## 4. Proposed Retention Summary (Unapproved)

*All retention periods listed below are strictly PROPOSED and require executive/legal signoff before any destructive purging can be enabled:*
- **Operational Webhook Deliveries**: 30 Days
- **Integration Ingest/Provisioning Logs**: 90 Days
- **Dead-Letter Failures**: 180 Days
- **Resolved Reconciliation Issues**: 1 Year
- **Audit Logs & Impersonation Sessions**: 7 Years
- **User Anonymization Execution**: On-demand upon verified privacy request
