# VibeConnect Architecture & Setup Guide

**Platform Version:** Phase 7  
**Architecture:** Multi-Tenant SaaS Master Control Plane (Django REST Framework + React TypeScript)  
**Last Updated:** Phase 7G  

---

## 1. System Overview

VibeConnect is an enterprise SaaS multi-tenant master control plane platform. It is engineered to govern independent systems (such as LMS, HRMS, VMS, and CRM) with strict tenant isolation, role-based access control, centralized identity, and versioned APIs.

### Core Architectural Principles:
1. **Zero Hardcoding:** All endpoints, domains, ports, database credentials, and secrets resolve through environment variables and centralized configuration.
2. **Tenant Isolation:** Every request resolves dynamically from the authenticated user and tenant organization context. Cross-tenant data leakage is strictly prohibited.
3. **Master Setup Authority:** Centralized catalog, plan versioning, and commercial entitlements govern tenant access.
4. **PostgreSQL Only:** SQLite is strictly blocked in code. All data models mandate PostgreSQL.
5. **Fail-Fast Configuration:** If required environment variables are absent, the application refuses to boot rather than falling back to insecure defaults.

---

## 2. Repository Layout

```
VibeConnect-Platform/
├── backend/
│   ├── apps/
│   │   ├── identity/          # PlatformUser, auth lifecycle, impersonation, user anonymization
│   │   ├── organizations/     # Multi-tenant organization boundaries & memberships
│   │   ├── product_registry/  # Products, modules, features & capability catalog
│   │   ├── plans/             # Commercial plans, versions, packaging & pricing
│   │   ├── subscriptions/     # Commercial organization subscriptions & entitlements
│   │   ├── entitlements/      # Direct commercial product grants & seat allocations
│   │   ├── access_control/    # RBAC, console modules, roles, permissions & tenant ceilings
│   │   ├── assignments/       # User product & module seat assignments
│   │   ├── auditlog/          # Immutable compliance audit log ledger & retention
│   │   ├── branding/          # Multi-tenant custom styling & themes
│   │   ├── notifications/     # Notification templates, delivery logs & async worker queue
│   │   ├── onboarding/        # Self-service organization onboarding & trial transitions
│   │   ├── invitations/       # Tenant user invitations & token validation
│   │   ├── bulk_import/       # Asynchronous CSV bulk user/seat import & error reporting
│   │   ├── access_requests/   # Member product access requests & ceiling-validated approvals
│   │   ├── showcase/          # Product portfolio & interactive presenter mode
│   │   ├── integration_hub/   # Connector instances, LMS connector, retries & dead-letter queue
│   │   ├── developer_console/ # Developer applications, SHA-256 API keys & webhooks
│   │   ├── reports/           # Platform metrics & tenant reporting catalogue
│   │   └── usage_metering/    # Metered usage telemetry ingestion & quota buckets
│   ├── common/                # Shared utilities, structured logging, correlation IDs & health probes
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py        # Shared configuration & strict PostgreSQL parser
│   │   │   ├── local.py       # Local development settings (env-driven)
│   │   │   └── production.py  # Production security settings (env-driven)
│   │   ├── asgi.py            # ASGI entry point
│   │   ├── wsgi.py            # WSGI entry point
│   │   └── urls.py            # Root routing (/api/v1/ prefix)
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example           # Verified backend environment template
│   └── .env.local             # Local development environment (ignored by Git)
├── frontend/
│   ├── src/
│   │   ├── api/               # Single centralized API client & versioned endpoints
│   │   ├── components/        # Reusable UI components & AppShell layout
│   │   ├── config/            # Strict env.ts validation & tenant module registries
│   │   ├── context/           # AuthContext & ThemeContext
│   │   ├── pages/             # Platform Owner & Tenant Admin workspaces
│   │   ├── routes/            # AppRoutes with role & tenant permission guards
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── .env.example           # Verified frontend environment template
├── docs/
│   ├── architecture_and_setup.md
│   ├── closeout_2G_3F.md
│   ├── phase_audit_report.md
│   └── runbooks/              # Authoritative operational runbooks (Phases 7A–7G)
│       ├── 01_application_startup_and_configuration.md
│       ├── 02_manual_deployment_and_code_rollback.md
│       ├── 03_database_backup_and_restore.md
│       ├── 04_disaster_recovery_and_data_consistency.md
│       ├── 05_observability_and_incident_response.md
│       ├── 06_integration_and_dead_letter_recovery.md
│       ├── 07_security_and_access_boundary_operations.md
│       └── 08_release_gates_and_production_handoff.md
├── backups/                   # Historical Phase 2C development SQL dumps (NOT production recovery points)
├── .gitignore
└── README.md
```

---

## 3. Database Policy & PostgreSQL Mandate

- **PostgreSQL Only:** VibeConnect strictly mandates PostgreSQL 15+ from its initial migration.
- **SQLite Strictly Prohibited:** SQLite drivers and database files are mechanically blocked in `backend/config/settings/base.py`.
- **Database Driver:** `psycopg 3` (`psycopg[binary]>=3.2.0`) is configured.
- **Strict Isolation:** VibeConnect maintains a separate dedicated database (`vibeconnect_local` / production DB) and role (`vibeconnect_app`). External systems (such as the LMS) must never connect directly to or query the VibeConnect database.
- **Connection Variable:** Configured exclusively through `DATABASE_URL`.

---

## 4. Environment Variables Configuration

### 4.1. Backend Configuration (`backend/.env` / `backend/.env.local`)
Create or edit `backend/.env.local` using the keys defined in `backend/.env.example`:

```env
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=<generate-high-entropy-secret-key>
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://vibeconnect_app:<PASSWORD>@localhost:5432/vibeconnect_local
CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173
DJANGO_SESSION_COOKIE_NAME=vibeconnect_sessionid
DJANGO_CSRF_COOKIE_NAME=vibeconnect_csrftoken
DJANGO_SESSION_COOKIE_AGE=28800
DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE=True
DJANGO_SESSION_SAVE_EVERY_REQUEST=True
DJANGO_SESSION_COOKIE_SECURE=False
DJANGO_CSRF_COOKIE_SECURE=False
DJANGO_SESSION_COOKIE_SAMESITE=Lax
DJANGO_CSRF_COOKIE_SAMESITE=Lax
DJANGO_AUTH_LOGIN_THROTTLE_RATE=5/minute
DJANGO_INVITATION_ISSUE_THROTTLE_RATE=30/minute
DJANGO_INVITATION_VALIDATE_THROTTLE_RATE=60/minute
DJANGO_INVITATION_ACCEPT_THROTTLE_RATE=10/minute
DJANGO_DEVELOPER_API_RATE_LIMIT=120/minute
VIBECONNECT_LMS_M2M_SECRET=<shared-m2m-secret>
VIBECONNECT_LMS_BACKEND_URL=http://localhost:8000
DJANGO_LOG_LEVEL=INFO
DJANGO_LOG_FORMAT=json
```

> [!IMPORTANT]
> In production, `DJANGO_SETTINGS_MODULE` must be `config.settings.production`, `DJANGO_DEBUG` must be `False`, and both `DJANGO_SESSION_COOKIE_SECURE` and `DJANGO_CSRF_COOKIE_SECURE` must be `True`.

### 4.2. Frontend Configuration (`frontend/.env` / `frontend/.env.local`)
Create `frontend/.env.local` using the keys defined in `frontend/.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_CSRF_COOKIE_NAME=vibeconnect_csrftoken
```

---

## 5. Local Development Execution

### 5.1. Database Migrations
```bash
# Execute within backend/ using local virtual environment
python manage.py migrate --settings=config.settings.local
```

### 5.2. Running Backend Locally
```bash
python manage.py runserver 8000 --settings=config.settings.local
```

### 5.3. Running Background Workers Locally
```bash
# General async queue (bulk import, notifications)
python manage.py run_worker

# Process integration retries
python manage.py process_integration_retries
```

### 5.4. Running Frontend Locally
```bash
cd frontend
npm install
npm run dev
```

### 5.5. Running Frontend Production Build
```bash
cd frontend
npm run build
```

---

## 6. Health & Readiness Monitoring

- **Liveness Probe:** `GET /api/v1/health/` (Process response; zero DB call; returns HTTP 200).
- **Readiness Probe:** `GET /api/v1/health/ready/` (Executes PostgreSQL `SELECT 1;`; returns HTTP 200 or 503).

---

## 7. Production Operations & Runbooks

For production deployment, backup restoration, incident management, integration recovery, and security protocols, refer to the authoritative runbooks:

- [Runbook 01: Application Startup & Configuration](runbooks/01_application_startup_and_configuration.md)
- [Runbook 02: Manual Deployment & Code Rollback](runbooks/02_manual_deployment_and_code_rollback.md)
- [Runbook 03: Database Backup & Restore](runbooks/03_database_backup_and_restore.md)
- [Runbook 04: Disaster Recovery & Data Consistency](runbooks/04_disaster_recovery_and_data_consistency.md)
- [Runbook 05: Observability & Incident Response](runbooks/05_observability_and_incident_response.md)
- [Runbook 06: Integration & Dead-Letter Recovery](runbooks/06_integration_and_dead_letter_recovery.md)
- [Runbook 07: Security & Access Boundary Operations](runbooks/07_security_and_access_boundary_operations.md)
- [Runbook 08: Release Gates & Production Handoff](runbooks/08_release_gates_and_production_handoff.md)
