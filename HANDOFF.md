# Handoff — FastAPI backend (`backend_py`)

**Status:** Phases 0–12 complete. 210 tests + 94 subtests pass; `ruff` clean; `compileall` clean.
**Reference implementation:** `backend/` (Node.js + Express 5 + Sequelize + MySQL) — unchanged.

---

## 1. Run it

```powershell
cd backend_py
uv sync
uv run python -m app.main      # or: uv run uvicorn app.main:app --port 8000
```

- API base: `http://localhost:8000/api/v1`
- Health: `GET /health` and `GET /api/v1/health`
- Swagger UI: `/docs` and `/api/v1/docs`; spec at `/api/v1/docs/openapi.json`

### Authorizing in Swagger UI

Protected operations show a padlock. Click **Authorize** (top right), paste the **token only** from
`POST /api/v1/auth/login` into the `BearerAuth` field — Swagger sends it as
`Authorization: Bearer <token>`. The scheme is registered as `BearerAuth` (http/bearer) in the
OpenAPI document; `/health` and the docs routes stay public and unmarked.

Configuration is read from `backend_py/.env` (see `.env.example`). Variable names:
`NODE_ENV`, `PORT`, `TZ`, `DATABASE_URL` or `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`,
`DB_LOGGING`, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT`/`DB_POOL_RECYCLE`,
`CORS_ORIGINS`, `BODY_LIMIT_BYTES`, `BCRYPT_ROUNDS`, `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`REFRESH_TOKEN_EXPIRE_MINUTES`, `REFRESH_COOKIE_NAME`/`REFRESH_COOKIE_PATH`/
`REFRESH_COOKIE_DOMAIN`/`REFRESH_COOKIE_SAMESITE`/`REFRESH_COOKIE_SECURE`,
`ADMIN_NAME`/`ADMIN_USERNAME`/`ADMIN_EMAIL`/`ADMIN_PASSWORD`, `API_V1_PREFIX`.

The login response carries the 30-minute access token in the body; the 8-hour refresh token
is only ever an httpOnly cookie scoped to `/api/v1`. Every guarded route requires both: a valid
`Authorization: Bearer <access token>` and the presence of that `dairy_refresh_token` cookie, so
deleting the cookie ends the session even while the access token is valid. `POST
/api/v1/auth/refresh` trades the cookie for a new access token and `POST /api/v1/auth/logout`
clears it.

## 2. Verify

```powershell
uv run pytest -q
uv run ruff check app tests
uv run python -m compileall -q app tests
```

## 3. Seeders

```powershell
uv run python -m app.seeders.base_seed        # PRD categories + admin (idempotent)
uv run python -m app.seeders.fake_indian_data # demo farm data (writes rows)
```

The fake seeder commits once at the end and rolls back on error. Re-running duplicates sales and
expenses only (their natural keys contain random amounts — same as Node). It works with both modern
and legacy Faker APIs.

## 4. What is implemented

| Area | Endpoints | Roles |
| --- | --- | --- |
| Health/docs | `/health`, `/api/v1/health`, `/docs`, `/api/v1/docs` | public |
| Auth | `POST /auth/login`, `GET /auth/me` | public / any |
| Users | `GET/POST /users`, `GET/PUT /users/:id`, `PATCH /users/:id/status` | admin |
| Buffaloes | `GET /buffaloes/count`, `GET/POST /buffaloes`, `GET/PUT /buffaloes/:id` | admin + operator |
| Production | `GET /production/grid`, `/production/summary`, `/production/buffalo/:id`, `GET/POST /production` (single + bulk) | admin + operator |
| Stock | `GET /stock`, `GET /stock/history` | admin + operator |
| Wastage | `GET/POST /wastage` | admin + operator |
| Customers | `GET /customers`, `GET /customers/:id/balance`, `POST /customers`, `GET/PUT /customers/:id` | admin + operator |
| Sales | `GET/POST /sales`, `GET/PUT /sales/:id` | admin + operator |
| Invoices | `GET/POST /invoices`, `GET /invoices/:id`, `GET /invoices/:id/pdf`, `PATCH /invoices/:id/payment` | admin + operator |
| Expenses | `GET/POST /expenses/categories`, `GET /expense-categories`, `GET/POST /expenses`, `GET/PUT /expenses/:id` | admin |
| Reports | `GET /reports/profit` (admin), `GET /reports/production`, `GET /reports/dashboard` | admin / admin + operator |
| Soft delete | `DELETE /:resource/:id` for `buffaloes,customers,sales,invoices,expenses,production,wastage` | admin |

Response envelopes are intentionally not uniform — each route mirrors Node (`/sales` POST returns flat
fields, `/expenses` list adds `total_pages`, `/auth/me` uses snake_case timestamps, etc.).
See `API_PARITY.md` for the per-route contract and `SCHEMA_MAPPING.md` for the database mapping.

## 5. Known deviations from Node (deliberate)

1. **Impossible dates/months** (`2026-02-31`, `2026-13`) return 400 `VALIDATION_ERROR` with the Node
   message instead of reaching MySQL. Node's regex-only validator lets them through.
2. **`/reports/production` without `from`/`to`** returns an empty summary (`days_recorded: 0`).
   Node's schema allows omission but its query is undefined for missing bounds.
3. **Seeder dates** use the business date (`Asia/Kolkata`); the Node faker script uses UTC.
4. **Generated OpenAPI** is served at `/api/v1/docs/openapi.json`; Node's checked-in spec is stale.

## 6. Open decisions (unchanged from earlier phases)

1. Concurrency: keep Node's unlocked read-then-write for stock, or add MySQL `GET_LOCK`.
2. Soft-deleted unique rows: restore/overwrite on re-entry, or keep returning conflicts.
3. Payments: keep Node's overpayment behaviour, or enforce ADR-004.
4. Operator rights: Node allows sale/invoice edits; PRD §4 suggests create/view/print only.
5. Scope: password reset, customer sales history, CSV/PDF report exports are absent in Node.

## 7. Not done

- No live write-path parity run (Node suite mutates the live DB; it was not executed).
- Phases 9–11 and the report endpoints have unit/API coverage but no live side-by-side Node comparison.
- No CI configuration, Docker image, or frontend changes; `backend/` and `frontend/` are untouched.
