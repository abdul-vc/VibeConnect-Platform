# Runbook 01: Application Startup and Configuration

**Target Audience:** DevOps Engineers, Platform Administrators, Onboarding Developers  
**Document Classification:** Operational Runbook  
**Last Updated:** Phase 7G  

---

## 1. Verified Runtime Requirements

The following software versions have been verified directly against the repository code and configuration:

| Component | Required Version | Verification Source |
|---|---|---|
| **Python** | `3.12+` | Verified against Django 5.2 / modern typing syntax in `backend/` |
| **Node.js** | `20+` LTS | Verified against React 18 / TypeScript 5 / Vite in `frontend/` |
| **npm** | `10+` | Package manager for `frontend/package.json` |
| **PostgreSQL** | `15+` | Mandated database engine; `psycopg 3` (`psycopg[binary]>=3.2.0`) in `backend/requirements.txt` |
| **OS Support** | Linux / Windows (Dev) | Cross-platform Python/Node execution; production mandates Linux |

> [!CAUTION]
> **Database Policy: Zero SQLite Tolerance**  
> SQLite (`django.db.backends.sqlite3`) is strictly prohibited. The database configuration in `backend/config/settings/base.py` enforces `DATABASE_URL` parsing with PostgreSQL verification. Starting the backend without a valid PostgreSQL connection string fails immediately.

---

## 2. Startup Entry Points

### 2.1. Backend WSGI / ASGI
- **WSGI Entry Point (Synchronous HTTP):**  
  `backend/config/wsgi.py` exposes `application = get_wsgi_application()`.  
  In production, WSGI servers such as Gunicorn must point to `config.wsgi:application`.
- **ASGI Entry Point (Asynchronous Protocol Support):**  
  `backend/config/asgi.py` exposes `application = get_asgi_application()`.  
  Available for ASGI runtimes such as Uvicorn pointing to `config.asgi:application`.

### 2.2. Frontend Build Procedure
- **Tooling:** Vite + React + TypeScript
- **Build Command:**
  ```bash
  # Execute within the frontend/ directory
  cd frontend
  npm run build
  ```
- **Output Artifact:** Compiled static bundle generated in `frontend/dist/`.
- **Serving:** Static assets in `frontend/dist/` must be served via a web server (e.g., Nginx, Caddy, Cloudflare Pages, AWS S3/CloudFront) with client-side SPA routing (`index.html` fallback). `OPERATOR ACTION REQUIRED: Configure production static asset hosting`.

---

## 3. Verified Environment Variables

Every variable listed below is consumed directly by repository code. **Never introduce hardcoded values or default URL guesses.** If a mandatory variable is missing, the application fails fast.

### 3.1. Backend Environment Variables (`backend/.env` / OS Environment)

| Variable Name | Required? | Purpose / Usage | Sensitive? |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Yes | Django settings module path (e.g., `config.settings.production` or `config.settings.local`). | No |
| `DJANGO_SECRET_KEY` | Yes | Cryptographic secret for signing sessions, CSRF tokens, and hashes. Must be a 50+ character high-entropy string. | **YES** |
| `DJANGO_DEBUG` | Yes | Must be `False` in production. Setting to `True` enables debug error pages. | No |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated list of fully qualified domain names (e.g., `api.vibeconnect.example.com`). | No |
| `DATABASE_URL` | Yes | PostgreSQL connection URI: `postgresql://<user>:<password>@<host>:<port>/<dbname>`. | **YES** |
| `CORS_ALLOWED_ORIGINS` | Yes | Comma-separated list of origins allowed for cross-origin requests (e.g., `https://app.vibeconnect.example.com`). | No |
| `CSRF_TRUSTED_ORIGINS` | Yes | Comma-separated list of origins trusted for CSRF validation (e.g., `https://app.vibeconnect.example.com`). | No |
| `DJANGO_SESSION_COOKIE_NAME` | Optional | Name of the session cookie (default: `vibeconnect_sessionid`). | No |
| `DJANGO_CSRF_COOKIE_NAME` | Optional | Name of the CSRF cookie (default: `vibeconnect_csrftoken`). | No |
| `DJANGO_SESSION_COOKIE_AGE` | Optional | Session lifetime in seconds (default: `28800` / 8 hours). | No |
| `DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE`| Optional | Whether session expires on browser close (default: `True`). | No |
| `DJANGO_SESSION_SAVE_EVERY_REQUEST` | Optional | Refreshes session on every request (default: `True`). | No |
| `DJANGO_SESSION_COOKIE_SECURE` | Yes (Prod) | Enforces HTTPS-only cookies (mandated `True` in `config.settings.production`). | No |
| `DJANGO_CSRF_COOKIE_SECURE` | Yes (Prod) | Enforces HTTPS-only CSRF cookies (mandated `True` in `config.settings.production`). | No |
| `DJANGO_SESSION_COOKIE_SAMESITE` | Optional | SameSite attribute (default: `Lax`). | No |
| `DJANGO_CSRF_COOKIE_SAMESITE` | Optional | SameSite attribute (default: `Lax`). | No |
| `DJANGO_AUTH_LOGIN_THROTTLE_RATE` | Optional | Rate limit for authentication attempts (default: `5/minute`). | No |
| `DJANGO_INVITATION_ISSUE_THROTTLE_RATE` | Optional | Rate limit for issuing tenant invitations (default: `30/minute`). | No |
| `DJANGO_INVITATION_VALIDATE_THROTTLE_RATE` | Optional | Rate limit for validating invitations (default: `60/minute`). | No |
| `DJANGO_INVITATION_ACCEPT_THROTTLE_RATE` | Optional | Rate limit for accepting invitations (default: `10/minute`). | No |
| `DJANGO_DEVELOPER_API_RATE_LIMIT` | Optional | Rate limit for developer API requests (default: `120/minute`). | No |
| `VIBECONNECT_LMS_M2M_SECRET` | Yes | Shared secret for Machine-to-Machine token signing with downstream LMS. | **YES** |
| `VIBECONNECT_LMS_BACKEND_URL` | Yes | Base URL of the integrated LMS backend API (e.g., `https://lms-api.example.com`). | No |
| `DJANGO_LOG_LEVEL` | Optional | Logging severity threshold: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`). | No |
| `DJANGO_LOG_FORMAT` | Optional | Formatter selection: `json` (production structured JSON) or `standard` (default: `json`). | No |

### 3.2. Frontend Environment Variables (`frontend/.env` / Build Environment)

| Variable Name | Required? | Purpose / Usage | Sensitive? |
|---|---|---|---|
| `VITE_API_BASE_URL` | Yes | Fully qualified base URL of the VibeConnect backend API (e.g., `https://api.vibeconnect.example.com`). Embedded during build. | No |
| `VITE_CSRF_COOKIE_NAME` | Yes | Name of the CSRF cookie to read for mutation headers (must match `DJANGO_CSRF_COOKIE_NAME`, e.g., `vibeconnect_csrftoken`). | No |

---

## 4. Liveness and Readiness Probes

VibeConnect exposes two distinct health monitoring endpoints under `/api/v1/health/`:

### 4.1. Liveness Probe (`GET /api/v1/health/`)
- **Purpose:** Verifies that the application process is running and able to handle HTTP requests.
- **Dependency Execution:** ZERO database or external service calls.
- **Response:** HTTP 200 `{"status": "ok", "app": "VibeConnect SaaS Control Plane"}`.
- **Use Case:** Kubernetes/orchestrator liveness check, container process restart trigger.

### 4.2. Readiness Probe (`GET /api/v1/health/ready/`)
- **Purpose:** Verifies that the application process can connect to and query PostgreSQL.
- **Dependency Execution:** Executes `connection.ensure_connection()` and `cursor.execute("SELECT 1;")`.
- **Response:**
  - On Success: HTTP 200 `{"status": "ready", "database": "healthy"}`.
  - On Failure: HTTP 503 `{"status": "unhealthy", "database": "unreachable", "error": "<redacted_reason>"}`.
- **Use Case:** Load balancer / reverse proxy target health check; prevents routing traffic to pods before database connectivity is established.

---

## 5. Background Worker Startup and Execution

VibeConnect employs PostgreSQL-backed asynchronous queues for job processing. Background workers must be managed as persistent services in production.

### 5.1. General Async Worker (`run_worker`)
- **Scope:** Processes queued `BackgroundJob` records, including bulk user/seat imports and async notification dispatches.
- **Command:**
  ```bash
  # Continuous daemon processing (polls every 2.0s when queue is idle)
  python manage.py run_worker

  # Bounded execution (processes existing queue items and exits)
  python manage.py run_worker --once

  # Custom poll interval and job limits
  python manage.py run_worker --poll-interval 5.0 --limit 100
  ```
- **Operational Responsibility:** Must be executed under a process supervisor (e.g., systemd, supervisord, container init). `OPERATOR ACTION REQUIRED: Configure worker service supervisor`.

### 5.2. Integration Retry Worker (`process_integration_retries`)
- **Scope:** Processes scheduled retries for failed integration events and provisioning tasks (`IntegrationFailure.status == RETRY_SCHEDULED`).
- **Command:**
  ```bash
  # Processes a bounded batch of up to 50 eligible retries and exits
  python manage.py process_integration_retries --limit 50
  ```
- **Execution Model:** Designed for periodic execution via a cron schedule or periodic job runner (e.g., every 1 to 5 minutes). `OPERATOR ACTION REQUIRED: Schedule periodic integration retry cron`.

### 5.3. Stuck Job Detection (`detect_stuck_integration_jobs`)
- **Scope:** Identifies orphaned `QUEUED` or `PROCESSING` provisioning jobs exceeding age thresholds.
- **Command:**
  ```bash
  python manage.py detect_stuck_integration_jobs --limit 50 --queued-threshold 300 --processing-threshold 600
  ```
- **Execution Model:** Periodic diagnostic check (e.g., every 15 minutes) to surface stalled jobs.

---

## 6. Safe Handling of Missing Configuration

1. **Fail-Fast Policy:** If `DATABASE_URL`, `DJANGO_SECRET_KEY`, `VITE_API_BASE_URL`, or `VITE_CSRF_COOKIE_NAME` are missing, the system will raise an explicit configuration error and refuse to boot.
2. **Zero Insecure Fallbacks:**
   - Never inject `localhost` or `127.0.0.1` into production configurations.
   - Never generate dynamic random keys on startup (doing so invalidates sessions on process restart and breaks multi-process deployments).
   - Never allow `DEBUG = True` in production environments.
