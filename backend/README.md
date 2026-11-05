# Dairy Management System â€” FastAPI backend

Async REST API for the single-farm dairy system: buffaloes, production, stock/wastage,
customers, sales, invoices/payments, expenses, reports â€” plus the **customer portal**
(activation, milk orders, invoices/PDF/balance, support queries).

- Python 3.11+, FastAPI, SQLAlchemy 2.1 async (`asyncmy`), MySQL 8, Alembic
- Money and litres are `DECIMAL` end to end and serialised as 2-decimal strings
- Business dates use `Asia/Kolkata` (`app/utils/time.py`)

The legacy Node backend in `../backend` is not used by this service and was not modified.

---

## 1. Setup

```powershell
Set-Location -LiteralPath 'D:\Projects\dairy_management_system\backend_py'
uv sync                                  # create .venv and install the lockfile
Copy-Item .env.example .env              # then edit the values you need
uv run alembic upgrade head              # 0001_baseline .. 0006_login_lockout
uv run uvicorn app.main:app --reload     # http://localhost:8000
```

`app/core/config.py` reads `backend_py/.env` and lets real environment variables win,
so the same file works as a template.

### Environment variables (names only â€” never commit values)

| Group | Variables |
| --- | --- |
| Server | `PORT`, `NODE_ENV`, `TZ`, `CORS_ORIGINS`, `API_V1_PREFIX`, `BODY_LIMIT_BYTES` |
| Database | `DATABASE_URL` (optional `mysql://â€¦`), or `DB_DIALECT`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`; plus `DB_LOGGING`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` |
| Staff auth | `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_MINUTES`, `BCRYPT_ROUNDS` |
| Staff cookies | `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_PATH`, `REFRESH_COOKIE_DOMAIN`, `REFRESH_COOKIE_SAMESITE`, `REFRESH_COOKIE_SECURE`, `SESSION_HINT_COOKIE_NAME` |
| Bootstrap admin | `ADMIN_NAME`, `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` |
| Customer auth | `CUSTOMER_JWT_SECRET` (empty means "reuse `JWT_SECRET`"), `CUSTOMER_ACTIVATION_TTL_HOURS`, `CUSTOMER_REFRESH_COOKIE_NAME`, `CUSTOMER_SESSION_HINT_COOKIE_NAME` |
| Order limits | `CUSTOMER_ORDER_MIN_LITRES`, `CUSTOMER_ORDER_MAX_LITRES`, `CUSTOMER_ORDER_DAILY_CAP_LITRES`, `CUSTOMER_ORDER_WINDOW_DAYS` |
| Login protection | `LOGIN_COOLDOWN_THRESHOLD`, `LOGIN_COOLDOWN_MINUTES`, `LOGIN_LOCKOUT_THRESHOLD`, `LOGIN_LOCKOUT_WINDOW_MINUTES` |
| Failed-login alerts | `FAILED_LOGIN_ALERT_ENABLED`, `FAILED_LOGIN_ALERT_THRESHOLD`, `FAILED_LOGIN_ALERT_WINDOW_MINUTES`, `FAILED_LOGIN_ALERT_COOLDOWN_MINUTES` |
| Mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `SMTP_TIMEOUT_SECONDS`, `MAIL_FROM_EMAIL`, `MAIL_FROM_NAME`, `FRONTEND_URL`, `PASSWORD_RESET_TTL_MINUTES` |

Set a distinct `CUSTOMER_JWT_SECRET` in production so staff and customer tokens cannot be
confused for one another.

### Auth model

- **Staff:** `Authorization: Bearer <access>` **and** the httpOnly `dairy_refresh_token`
  cookie. A bare token is rejected, so removing the cookie signs the session out.
- **Customer:** separate `customer_access` tokens (`scope="customer"`,
  `aud="customer-portal"`) plus the `dairy_customer_refresh_token` cookie. Staff guards
  reject customer tokens and customer guards reject staff tokens.

---

## 2. Migrations

```powershell
uv run alembic current          # what the database is at
uv run alembic upgrade head     # apply 0001_baseline .. 0006_login_lockout
uv run alembic downgrade -1     # roll the latest revision back
```

Every revision is **idempotent**: it creates only the tables, columns, indexes and
foreign keys that are missing (`app/db/migration_helpers.py`), so
`alembic upgrade head` can be re-run on a fresh volume, on the legacy Sequelize
database, or on a database left behind by an interrupted run without failing with
"table already exists" / "duplicate column name" / "duplicate key name". The chain is
`0001_baseline` to `0006_login_lockout`.

Under Docker the backend container does this by itself: `docker-entrypoint.sh` waits
for MySQL, runs the migrations, ensures the base seed data, then starts Uvicorn. Use
the plain `alembic` command inside the container - the image has no `uv.lock`, so
`uv run` is the wrong prefix there:

```bash
docker compose exec backend alembic upgrade head
```

`0002_customer_portal` is **purely additive** â€” it creates
`customer_portal_accounts`, `customer_portal_account_events`, `customer_orders`,
`customer_order_events`, `customer_queries` and `customer_query_messages`, and does not
alter any existing table or row. `0003_password_reset` adds the
`password_reset_tokens` table (SHA-256 hashes only, one row per issued link).
`0004_token_version` adds `token_version` (default `0`) to `users` and
`customer_portal_accounts` so a password reset or deactivation can invalidate every
session issued earlier. Take a backup before applying any migration to a live database.

---

## 3. API map (prefix `/api/v1`)

Interactive docs: `GET /api/v1/docs`, OpenAPI: `GET /api/v1/docs/openapi.json`,
health: `GET /health`.

| Area | Endpoints | Access |
| --- | --- | --- |
| Staff auth | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/forgot-password`, `GET /auth/reset-password/validate`, `POST /auth/reset-password`, `GET /auth/me` | public / staff |
| Users | `GET/POST /users`, `GET /users/{id}`, `PATCH /users/{id}/status`, `DELETE /users/{id}` | admin |
| Buffaloes | `GET /buffaloes`, `GET /buffaloes/count`, `POST /buffaloes`, `GET /buffaloes/{id}` | admin, operator |
| Production | `GET /production`, `GET /production/grid`, `GET /production/summary`, `GET /production/buffalo/{id}`, `POST /production` | admin, operator (operator: current day only) |
| Stock / wastage | `GET /stock`, `GET /stock/history`, `GET/POST /wastage` | admin, operator |
| Customers | `GET/POST /customers`, `GET /customers/{id}`, `GET /customers/{id}/balance` | admin, operator |
| Sales | `GET/POST /sales`, `GET /sales/{id}` | admin, operator |
| Invoices | `GET/POST /invoices`, `GET /invoices/{id}`, `GET /invoices/{id}/pdf`, `PATCH /invoices/{id}/payment` | admin, operator |
| Expenses | `GET/POST /expenses`, `GET /expenses/{id}`, `GET/POST /expenses/categories`, `â€¦/expense-categories` alias | admin |
| Reports | `GET /reports/profit` (admin), `GET /reports/production`, `GET /reports/dashboard`, `GET /reports/pdf` | admin, operator |
| Deletion | `DELETE /{resource}/{id}` (soft delete) | admin |
| Portal accounts (staff) | `GET /customer-portal-accounts`, `GET /{id}`, `POST`, `POST /{id}/reactivate`, `POST /{id}/deactivate`, `POST /{id}/reset-activation` | read: admin+operator; writes: admin |
| Customer orders (staff) | `GET /customer-orders`, `GET /{id}`, `POST /{id}/approve`, `POST /{id}/reject`, `POST /{id}/fulfil`, `POST /{id}/cancel` | admin, operator |
| Customer queries (staff) | `GET /customer-queries`, `GET /{id}`, `POST /{id}/messages`, `POST /{id}/status`, `POST /{id}/assign` (admin only) | admin, operator |
| Customer auth | `POST /customer-auth/activate`, `POST /customer-auth/login`, `POST /customer-auth/refresh`, `POST /customer-auth/logout`, `POST /customer-auth/forgot-password`, `GET /customer-auth/reset-password/validate`, `POST /customer-auth/reset-password`, `GET /customer-auth/me` | public / customer |
| Customer portal | `GET /customer-portal/dashboard`, `GET /profile`, `GET /balance`, `GET/POST /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `GET /invoices`, `GET /invoices/{id}`, `GET /invoices/{id}/pdf`, `GET/POST /queries`, `GET /queries/{id}`, `POST /queries/{id}/messages` | customer only |

Errors are uniform: `{"error": {"code": "â€¦", "message": "â€¦"}}`. Additive portal codes
include `STOCK_BUSY` (503), `INVALID_ORDER_TRANSITION` / `INVALID_QUERY_TRANSITION` /
`QUERY_CLOSED` (409), and `ORDER_DAILY_LIMIT_EXCEEDED`, `ORDER_LIMIT_EXCEEDED`,
`INVALID_FULFILMENT_DATE`, `STOCK_INSUFFICIENT` (400). Quantity and requested-date
window violations arrive as `400 VALIDATION_ERROR` from the request schema.

---

## 4. Orders, reservations and stock

1. A customer order records the quantity (1.00â€“500.00 L), the requested date
   (today â€¦ today+14) and a **rate snapshot**; the server computes
   `total = quantity Ã— rate` (HALF_UP, 2 dp). Nothing touches stock or revenue yet.
2. Staff approval reserves the litres for that date and every later date with stock rows
   (`closing âˆ’ approved_reserved â‰¥ 0` at each). Rejection and cancellation release the
   reservation.
3. Fulfilment is only possible on/after the requested date (operator: that day only,
   admin: that day or later) and creates exactly **one** sale with the order's rate plus
   **one** unpaid invoice, atomically.
4. Stock-mutating paths (sale create/edit, approve, fulfil, staff cancel) run inside the
   MySQL advisory lock `dairy:stock`; contention returns `503 STOCK_BUSY` so the caller can
   retry. Pending/approved orders never count as sales, revenue, profit or physical stock
   movement.

---

## 5. Password reset and session revocation

`POST /auth/forgot-password` and `POST /customer-auth/forgot-password` always return the
same message, whether or not the address exists, and the email is sent from a FastAPI
background task so response time does not leak account existence. The emailed link is
single-use, expires, and is scoped to staff or customer.

A successful reset bumps the subject's `token_version`, so every access and refresh token
issued earlier is rejected with `401 UNAUTHORIZED` / "Session has expired; sign in again";
the user signs in again with the new password. Deactivating or reactivating a portal
account bumps the same counter, as do an admin password change and a staff
deactivation/reactivation or soft delete. A deactivated staff account is blocked even
before the bump; the bump is what stops the old token from working again after reactivation.

---

## 6. Failed-login cooldown, lockout and alerts

`app/services/login_lockout.py` owns the state machine used by both sign-in surfaces
(`app/services/auth_service.py` and `app/services/customer_portal_auth_service.py`).

| Attempt | Result |
| --- | --- |
| Wrong password, burst below `LOGIN_COOLDOWN_THRESHOLD` | `401 UNAUTHORIZED`, counter incremented |
| Burst reaches the threshold (default 5) | Alert email, then `429 TOO_MANY_ATTEMPTS` |
| Any attempt while the pause runs | `429`, refused before the password is checked, counter unchanged |
| Counted failures reach `LOGIN_LOCKOUT_THRESHOLD` (default 10) | `403 ACCOUNT_LOCKED`; `is_active=False`, `locked_at` set, `token_version` bumped. Permanent: no timer, only an administrator unlock (`clear_lock`) re-activates the account |

**State.** Nothing is stored in memory or in a cookie: the pause is derived from
`failed_login_count` and `failed_login_first_at` on the account row
(`app/models/user.py`, `app/models/customer_portal_account.py`). A closed tab, a reload, a
different browser or an API restart therefore cannot shorten it, and attempts made while
it runs are not counted, so they cannot escalate into a lock.

**Clock.** `register_failed_attempt` resets `failed_login_first_at` at the moment the
threshold is reached, so the pause always lasts the full `LOGIN_COOLDOWN_MINUTES`. (If it
were measured from the first failure, a slow burst of five guesses could finish after the
pause had already elapsed.) `burst_expires_at` adds the pause back to the counting window
so the burst is not considered stale while it is blocked.

**Response contract.** `cooldown_error()` returns `429` with the standard envelope plus
machine-readable fields, and `cooldown_message()` builds the prose from settings:

```json
{
  "error": {
    "code": "TOO_MANY_ATTEMPTS",
    "message": "Too many failed sign-in attempts. Sign-in is paused for 5 minutes after 5 failed attempts. Try again in 2 minutes 8 seconds.",
    "retry_after_seconds": 128,
    "cooldown_minutes": 5,
    "cooldown_threshold": 5
  }
}
```

The `Retry-After` header carries the same seconds. `_error_response` in
`app/routers/auth.py` and `app/routers/customer_auth.py`, and the global handler in
`app/core/errors.py`, preserve those extra keys instead of trimming the body to
`code`/`message`.

**Changing the window.** Edit `LOGIN_COOLDOWN_MINUTES` (and/or
`LOGIN_COOLDOWN_THRESHOLD`) in `backend_py/.env` and restart the API. Because both the
message and the structured fields are built from `settings` at call time, the login pages,
API clients, logs and the alert email all follow with no code change. `docker-compose.yaml`
also forwards these variables, so the container sees the same values.

**Mail.** `app/services/email_service.py` renders all five messages
(`send_password_reset`, `send_password_changed`, `send_failed_login_alert`,
`send_account_locked_notice`, `send_portal_activation`) through one inline-styled,
table-based shell: hidden preheader, brand bar with a tone-coded status pill, accent rule,
details table, numbered steps, tinted callout and a matching plain-text part. No external
images, fonts or scripts, so the layout holds in Gmail, Outlook and mobile clients.

---

## 7. Tests and checks

```powershell
Set-Location -LiteralPath 'D:\Projects\dairy_management_system\backend_py'
uv run ruff check app tests
uv run python -m compileall -q app tests
uv run pytest -q
```

Current baseline: **388 passed / 150 subtests**, ruff clean, compileall exit 0
(2026-11-03); `npm run lint` and `npm run build` also pass in `frontend/`.
Tests use fakes and dependency overrides; they never open the live database.
The Windows pytest-cache permission warning is benign; the local `.env` may also make
PyJWT warn that a development signing key is shorter than 32 bytes (production rejects
such a key at startup).

See `../docs/CUSTOMER_PORTAL_UAT_RELEASE.md` for the UAT script, release checklist and
backup/rollback procedure.
