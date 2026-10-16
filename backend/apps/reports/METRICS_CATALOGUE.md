# VibeConnect Phase 6E — Authoritative Metrics Catalogue

## 1. Product Adoption Metric

- **Business Definition:** Measures tenant adoption and end-user penetration of registered products. Expressed as the count of active tenant organizations entitled to a product, and the count of active end-users assigned to the product.
- **Authoritative Source Table & Fields:**
  - Tenant Adoption: `OrganizationProductEntitlement` (`apps/entitlements/models.py`), fields `organization_id`, `product_id`, filtered by `status = 'active'`.
  - User Penetration: `UserProductAssignment` (`apps/assignments/models.py`), fields `organization_id`, `product_id`, `user_id`, filtered by `status = 'active'`.
- **Event & Scope Semantics:**
  - Temporal behavior: Point-in-time active entitlement and assignment counts, with historical trend based on `created_at`.
  - Tenant/Product Scope: Filterable by individual `organization_id` and `product_id` or aggregated platform-wide.
  - Data Freshness: Real-time transactional database state.
- **Historical Data Availability:** Fully available since Phase 2A (Entitlements) and Phase 2F (Assignments).

---

## 2. Seat Utilization Metric

- **Business Definition:** Measures allocated user seats against entitled subscription/plan seat limits. Expressed as allocated active seats, total entitled seat quota, and seat utilization percentage.
- **Authoritative Source Table & Fields:**
  - Assigned Seats: `UserProductAssignment` (`apps/assignments/models.py`), count of rows with `organization_id`, `status = 'active'`.
  - Seat Quota Limit: `SubscriptionProductEntitlement.quota_allocated` (`apps/subscriptions/models.py`) or plan quota (`PlanQuota.limit_value`).
  - Calculation Service: Authoritative calculation reused from `apps/assignments/services/effective_access.py:75-80`.
- **Event & Scope Semantics:**
  - Tenant Scope: Strictly scoped to tenant organization.
  - Data Freshness: Real-time transactional state.
- **Historical Data Availability:** Fully available since Phase 2C (Subscriptions) and Phase 2F (Assignments).

---

## 3. SSO Launch Activity Metric

- **Business Definition:** Measures SSO authentication traffic and control-plane token exchange handoff volume between VibeConnect and downstream integrated applications (e.g., LMS).
- **Authoritative Source Table & Fields:**
  - Source Model: `SsoAuthorizationCode` (`apps/integration_hub/models.py:733`).
  - Code Issuance: Count of authorization codes issued within the reporting window (`created_at__gte=start_dt, created_at__lte=end_dt`).
  - Code Validation / Exchange: Count of authorization codes validated/exchanged within the reporting window (`used_at__gte=start_dt, used_at__lte=end_dt`).
- **Independent Event-Volume Semantics (No Derived Percentage):**
  - **Codes Issued:** Represents the total volume of SSO handoff attempts initiated by users in VibeConnect during the reporting window.
  - **Codes Exchanged / Validated:** Represents the total volume of one-time authorization codes successfully exchanged for tokens by downstream applications during the reporting window.
  - **Cohort Incompatibility:** Because codes issued near the boundary of a reporting period may be exchanged in a subsequent window (or codes exchanged early in the window were issued prior to it), these two counts reflect independent event volumes across distinct timestamps rather than a closed, single cohort. Consequently, no derived completion rate or percentage is computed across these incompatible cohorts, preventing mathematically distorted values (e.g., rates exceeding 100% or misrepresenting carry-over codes).
  - **Downstream Application UI Loading (Limitation):** `SsoAuthorizationCode.used_at` confirms successful cryptographic token exchange at the API boundary only. It does NOT represent or prove that the downstream application's client-side UI, SPA, or course player rendered successfully. Client-side downstream rendering is not observable inside the VibeConnect control plane.
- **Time-Window Behavior & Scope:** Bounded date ranges (`created_at__range` for issuance; `used_at__range` for validation). Scoped by `organization_id` and `product_id`.
- **Historical Data Availability:** Fully available since Phase 5B / Prompt 21.


---

## 4. Integration Health Trend Metric

- **Business Definition:** Component health status of integration connectors and background provisioning pipelines, categorizing tenant status as `healthy`, `degraded`, or `unhealthy`.
- **Authoritative Source Table & Fields:**
  - Source Models:
    - `ConnectorInstance` (`apps/integration_hub/models.py`): `status` (`active`, `suspended`, `disconnected`).
    - `IntegrationFailure` (`apps/integration_hub/models.py:101-190`): `status` (`open`, `retry_scheduled`, `dead_letter`, `resolved`).
    - `ProvisioningJob` (`apps/integration_hub/models.py`): `status` (`queued`, `processing`, `failed`, `completed`).
    - `IntegrationReconciliationIssue` (`apps/integration_hub/models.py:270`): `status` (`detected`, `resolved`, `ignored`).
  - Calculation Service: Reused directly from `apps/integration_hub/support_views.py:185-195` (from 6C-2).
- **Health Indicators (Transparent Components, No Composite Score):**
  - Dead-letter count (`dead_letter_failures`).
  - Stuck jobs count (from `detect_stuck_provisioning_jobs`).
  - Open failures count (`open_failures`).
  - Open reconciliation issues count.
- **Historical Data Availability:** Fully available since Phase 5G and Phase 6C.

---

## 5. Support Activity Volume Metric

- **Business Definition:** Measures operational support overhead and remediation throughput across failures retried, dead-letter records replayed, issues resolved, and impersonation sessions initiated.
- **Authoritative Source Table & Fields:**
  - Source Model: `AuditLog` (`apps/auditlog/models.py`), filtered by:
    - `action = 'support_failure_retry_scheduled'`
    - `action = 'support_dead_letter_replayed'`
    - `action = 'support_failure_resolved'`
    - `action = 'support_reconciliation_resolved'`
    - `action = 'support_impersonation_started'`
- **Event & Scope Semantics:**
  - Action counts grouped within bounded date range, reporting both remediation operations and impersonation session starts.
  - Scoped by `organization_id` or platform-wide.
- **Historical Data Availability:** Captured in audit log since Phase 6C-4 and 6D. Historical data does NOT exist prior to Phase 6C/6D rollout; zero backfill estimation is performed.

---

## 6. Impersonation Frequency & Duration Metric

- **Business Definition:** Measures audited Support Operator impersonation sessions, frequency of tenant assistance, and realized session duration.
- **Authoritative Source Table & Fields:**
  - Source Model: `SupportImpersonationSession` (`apps/identity/models.py:349`).
  - Session Frequency: Count of sessions by `created_at`.
  - Session Duration: Computed as `(terminated_at or expires_at) - created_at`, hard-capped at 1800 seconds (30 minutes).
  - Breakdown: Session counts grouped by `status` (`active`, `expired`, `terminated`, `revoked`).
- **Historical Data Availability:** Captured since Phase 6D. Zero historical estimation before Phase 6D.

---

## Source Gap Summary (Stage 6E-2 Determination)
All 6 candidate metrics map directly to existing, authoritative database models with complete schema fields.
**Result:** ZERO new instrumentation models or tables required for Phase 6E-2.
