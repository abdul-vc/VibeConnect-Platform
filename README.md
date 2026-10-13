# VibeConnect SaaS Master Platform

VibeConnect is an enterprise SaaS multi-tenant master control plane platform engineered to govern independent products (such as LMS, HRMS, VMS, and CRM) with strict tenant isolation, role-based access control, centralized identity, and versioned APIs.

---

## Architecture Overview
- **Backend**: Django 5.2, Django REST Framework, PostgreSQL 15+ (`psycopg 3`), modular settings (`config.settings.local`, `config.settings.production`).
- **Frontend**: React 18, TypeScript 5, Vite, centralized API client, tenant permission route guards.
- **Observability**: Structured JSON logging, `X-Request-ID` correlation context, sensitive string redaction, liveness (`/api/v1/health/`) and database readiness (`/api/v1/health/ready/`) probes.

---

## Repository Layout
- `backend/`: Django REST Framework control plane API and background workers.
- `frontend/`: React + TypeScript SPA application.
- `docs/`: Technical architecture documentation and operational runbooks.
- `backups/`: Historical Phase 2C development snapshots (reference only).

---

## Documentation & Operational Runbooks

For architecture details, local setup, and verified environment variables, see:
- [Architecture & Setup Guide](docs/architecture_and_setup.md)

For production operations, deployment, disaster recovery, and incident response, consult the authoritative runbook suite:
1. [Runbook 01: Application Startup & Configuration](docs/runbooks/01_application_startup_and_configuration.md)
2. [Runbook 02: Manual Deployment & Code Rollback](docs/runbooks/02_manual_deployment_and_code_rollback.md)
3. [Runbook 03: Database Backup & Restore](docs/runbooks/03_database_backup_and_restore.md)
4. [Runbook 04: Disaster Recovery & Data Consistency](docs/runbooks/04_disaster_recovery_and_data_consistency.md)
5. [Runbook 05: Observability & Incident Response](docs/runbooks/05_observability_and_incident_response.md)
6. [Runbook 06: Integration & Dead-Letter Recovery](docs/runbooks/06_integration_and_dead_letter_recovery.md)
7. [Runbook 07: Security & Access Boundary Operations](docs/runbooks/07_security_and_access_boundary_operations.md)
8. [Runbook 08: Release Gates & Production Handoff](docs/runbooks/08_release_gates_and_production_handoff.md)
