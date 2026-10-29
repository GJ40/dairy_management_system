# Progress — Python/FastAPI Migration

**Current phase:** Phase 12 complete — parity audit + handoff
**Last updated:** 2026-10-29
**Target:** `backend_py/` only
**Reference:** `backend/` (do not modify)

---

## Status at a glance

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Audit, plan, parity, schema mapping | **COMPLETE** |
| 1 | Foundation (settings, DB, errors, health, docs) | **COMPLETE** |
| 2 | SQLAlchemy models + Alembic baseline + live schema inspection | **COMPLETE** |
| 3 | Auth, users, RBAC | **COMPLETE** |
| 4 | Buffaloes + soft delete | **COMPLETE** |
| 5 | Production | **COMPLETE** |
| 6 | Stock + wastage | **COMPLETE** |
| 7 | Customers + sales | **COMPLETE** |
| 8 | Invoices + payments + PDF | **COMPLETE** |
| 9 | Expenses | **COMPLETE** |
| 10 | Dashboard + reports | **COMPLETE** |
| 11 | Faker seeders | **COMPLETE** (live fake-seed run pending) |
| 12 | Parity audit + handoff | **COMPLETE** |

Phase 1 is complete: configuration, async DB session, error handlers, middleware, health, docs,
`.env.example`, and stdlib tests are implemented. Phase 2 is complete: all 10 models match the live
schema exactly, and the Alembic baseline is stamped. `alembic_version` contains `0001_baseline`;
the database has 11 tables (the original 10 plus `alembic_version`). Phase 3 added login, JWT
authentication, `/auth/me`, admin user management, and RBAC. Phase 4 added buffalo CRUD/counts and
the admin-only generic soft-delete endpoint. Phase 5 added production grid/list/summary/history and
atomic single/bulk recording. Phase 6 added derived stock, stock history, wastage recording, and
wastage listing. Phase 7 added customers, balances, sales, stock guards, and sale updates. Phase 8 added invoices,
payments, and PDF rendering. Phase 9 added admin-only expense categories and expenses. 163 tests
passed at the end of Phase 8; no application DDL or live data change has been executed.

---

## Phase 0 deliverables

- `MIGRATION_PLAN.md` — structure, modules, endpoints, dependencies, PRD matrix, risks, order, Alembic strategy, seed plan.
- `API_PARITY.md` — 51 endpoints with auth, request/response envelopes, errors, test plan.
- `SCHEMA_MAPPING.md` — 10 tables, exact columns/types/constraints/indexes/FKs, baseline procedure.
- `PROGRESS.md` — this file.

Read-only inspection performed:

- All Node models, routes, services, repositories, validators, middleware, utils, seeders, tests, docs.
- `backend/.env.example` variable names only; no secret values printed.
- Frontend API modules and error handling.
- Confirmed `backend/prisma/` is empty and no `.sql` schema exists.
- Confirmed `backend_py` has no `.env`, no `alembic.ini`, no `alembic/env.py`, no tests, no code.
- Confirmed Python imports work: fastapi 0.162.0, sqlalchemy 2.1.6, alembic 1.20.1, asyncmy, bcrypt, PyJWT, reportlab, faker, pydantic-settings.
- At Phase 0, `pytest` and `ruff` were not installed; both were installed in Phase 3.

Not performed (no approval):

- No live MySQL connection/query/DDL/seed.
- Phase 0: no Alembic init/revision/stamp/upgrade (Phase 2 later created the config and an empty baseline).
- No package installation during Phase 0.
- No Node test run (they hit the live configured MySQL and mutate rows).

---

## Phase 1 implementation

Created:

- `app/core/config.py` — pydantic-settings, env aliases, masked secrets, async MySQL URL builder.
- `app/core/errors.py` — Node-compatible error envelope, 400 validation / 404 / 405 / 500 handlers.
- `app/core/middleware.py` — 1 MB body limit, Helmet-style headers, request logging.
- `app/core/logging.py` — root logging setup.
- `app/db/session.py` — async engine, session factory, DB health probe, dispose.
- `app/db/base.py` — declarative base for Phase 2 models.
- `app/routers/health.py` — `/health` + `/api/v1/health`.
- `app/routers/docs.py` — Swagger UI at `/docs` and `/api/v1/docs`.
- `app/main.py` — app factory, CORS, middleware order, OpenAPI at `/api/v1/docs/openapi.json`.
- `app/schemas/health.py`, `app/utils/time.py`.
- `.env.example` (placeholders only, no real secrets).
- `tests/test_phase1.py` — stdlib `unittest` + `httpx` smoke tests (no live DB).

Dependencies:

- Installed `greenlet==3.5.6` (approved) and declared it, plus `faker` and `tzdata`, in `pyproject.toml`.
- Set `[tool.uv] package = false`; removed the broken `backend-py = "backend_py:main"` script.
- `uv lock` updated; `uv sync --check` reports no changes.

Verification:

- `uv run python -m unittest discover -s tests -v` → **11 tests passed**.
- `uv run python -m compileall -q app tests` → passed.
- Confirmed: `/health` and `/api/v1/health`; `/docs` and `/api/v1/docs`; generated OpenAPI at
  `/api/v1/docs/openapi.json`; 404/405 envelope; CORS preflight with credentials; security headers;
  1 MB body limit → 413; Asia/Kolkata business-date boundary.
- Settings load without `.env`; driver resolves to `mysql+asyncmy`; secrets render masked.
- No MySQL connection was opened; health DB check was mocked in tests.

Still missing tooling: `pytest`, `ruff` (stdlib `unittest` was used instead).

---

## Phase 2 implementation

Live inspection (read-only, approved):

- MySQL `8.0.33`; all 10 tables `InnoDB`, `utf8mb4`, `utf8mb4_0900_ai_ci`.
- No `alembic_version` table.
- 10 foreign keys, all `ON DELETE CASCADE ON UPDATE CASCADE`.
- Duplicate unique indexes confirmed:
  - `users`: `email`, `users_email`, `username`, `users_username`.
  - `buffaloes`: `tag_no`, `buffaloes_tag_no`.
  - `invoices`: `invoice_no`, `invoices_invoice_no`.
  - `expense_categories`: `name`, `expense_categories_name`.
  - `invoice_sales`: unique `sale_id` plus composite unique `(invoice_id, sale_id)`.
- `created_at`/`updated_at` are `DATETIME NOT NULL` with no DB default; timestamps are Python-side.
- No CHECK constraints; enums are application-validated `VARCHAR`.
- Snapshot: `C:\Users\GAURANG\AppData\Local\Temp\opencode\schema_snapshot.json`.

Created:

- `app/models/` — 10 SQLAlchemy 2.x models with exact live type, nullability, server defaults,
  index names, FK names/rules, engine, charset, and collation.
- `app/models/base.py` — `TimestampMixin`, `SoftDeleteMixin`, and timezone-naive timestamp helper.
- `alembic.ini` — no embedded URL; imports `settings` from `%(here)s`.
- `alembic/env.py` — async engine from `settings.sqlalchemy_database_url`, `Base.metadata` target.
- `alembic/script.py.mako`, `alembic/versions/0001_baseline_existing_schema.py` — empty baseline.
- `tests/test_models.py` — 12 no-DB tests for tables, indexes, cascades, decimals, timestamps,
  collation, and normalizers.

Verification:

- Metadata comparator vs live snapshot: **MATCH** (10 tables, columns, types, nullability,
  defaults, indexes, FKs, engine, collation).
- `uv run python -m unittest discover -s tests -v` → **23 tests passed**.
- `uv run python -m compileall -q app tests alembic` → passed.
- `alembic history` / `heads` → `0001_baseline (head)`.
- `alembic upgrade head --sql` → only `CREATE TABLE alembic_version` + baseline INSERT; no
  application DDL. Offline SQL generation opened no DB connection.
- `alembic stamp head` approved and executed → `alembic_version = 0001_baseline`.
- Post-stamp read-only check → 11 tables: the original 10 plus `alembic_version`; no application
  table was created, altered, or dropped.

Not performed:

- No application DDL, Alembic `upgrade`, or seed against MySQL.
- No live ORM writes; Phases 3–4 performed read-only list/get/count queries against the live
  `users` and `buffaloes` tables.
- No `backend_py/.env` was created; live commands read credentials transiently from the existing
  backend configuration without printing them.

---

## Phase 3 implementation

Created:

- `app/core/security.py` — bcrypt cost 10 with 72-byte truncation; HS256 JWT with
  `{id,email,username,role,iat,exp}`.
- `app/core/dependencies.py` — Bearer authentication, DB reload, deleted/inactive rejection,
  `require_roles`/`require_admin`, repository/service dependencies.
- `app/schemas/user.py` — login/create/update/status request validation, query parsing model,
  Node-compatible user serialization.
- `app/repositories/user_repository.py` — async user lookup, list/count, create, commit helpers.
- `app/services/auth_service.py` — login, generic credential errors, inactive check, `/auth/me`.
- `app/services/user_service.py` — admin list/create/get/update/status, duplicate checks,
  self-deactivation guard, normalized email/username, hashed passwords.
- `app/routers/auth.py`, `app/routers/users.py` — `/api/v1/auth/*` and admin-only `/api/v1/users`.
- `tests/test_phase3.py` — security, serialization, service, and API tests with fake repository/DB.
- `pyproject.toml` — installed `pytest`, `ruff`; added a conservative ruff config.

Contract details preserved:

- Login success returns `{token, user}`; login/list/user routes use `createdAt`/`updatedAt`.
- `/auth/me` returns `created_at`/`updated_at` (Node's snake-case attribute selection quirk).
- Generic login error for unknown email, wrong password, or soft-deleted user; inactive user gets
  the deactivation message only after a valid password.
- Admin-only user routes; operator gets 403 `Access denied: Requires one of [admin] role`.
- `POST /users` requires `role`, accepts password min 6, ignores `is_active`, and creates active
  users; duplicate email/username messages match Node.
- Update supports partial fields and optional password; self-deactivation returns 400.
- Validation errors are 400 `VALIDATION_ERROR` with `field: message`, not FastAPI 422.

Verification:

- `uv run pytest -q` → **72 passed** (including 23 prior tests).
- `uv run ruff check app tests` → clean.
- Read-only live smoke test: list users (`total=13`), email lookup, `/auth/me` shape, and service
  serialization succeeded; id 1 timestamp `2026-10-28 12:10:23` serialized to
  `2026-10-28T06:40:23.000Z`, matching Node.
- No live create/update/delete was executed.

---

## Phase 4 implementation

Created:

- `app/schemas/buffalo.py` — create/update validation, query model, exact errors, buffalo
  serialization with camel-case timestamps.
- `app/repositories/buffalo_repository.py` — non-deleted lookup, tag lookup, filtered list/count,
  status counts, create/commit helpers.
- `app/repositories/delete_repository.py` — generic soft delete by model and ID.
- `app/services/buffalo_service.py` — list/get/create/update/counts, tag normalization,
  duplicate messages, date conversion.
- `app/services/delete_service.py` — allowlist, admin soft delete, Node-compatible response and
  not-found messages.
- `app/routers/buffaloes.py`, `app/routers/delete.py` — `/api/v1/buffaloes/*` for admin+operator
  and admin-only `DELETE /api/v1/{resource}/{id}`.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py`, `app/utils/time.py` — wiring,
  validation labels, shared timestamp helper.
- `tests/test_phase4.py` — serialization, validation, service, delete, and API tests with fakes.

Contract details preserved:

- Both admin and operator can list, view, create, and update buffaloes.
- `tag_no` is trimmed and stored uppercased; status defaults to `active` on create.
- Dates are `YYYY-MM-DD` strings or null; update accepts explicit null to clear a date.
- List sorts `created_at DESC`, filters status/search, and hides deleted rows; counts exclude
  deleted rows and return fixed keys `total,active,dry,sold,dead`.
- Buffalo JSON: `id,tag_no,name,breed,dob,purchase_date,status,is_deleted,createdAt,updatedAt`.
- Generic soft delete supports `buffaloes,customers,sales,invoices,expenses,production,wastage`;
  it sets `is_deleted=true` without cascading and is admin-only.
- Node's not-found singularization quirk is preserved (`buffaloe`, `productio`, `wastag`).

Verification:

- `uv run pytest -q` → **103 passed**.
- `uv run ruff check app tests` → clean; compileall clean.
- Read-only live smoke test: `total=65`, counts `{active:57,dry:1,sold:6,dead:1}` matched Node
  exactly; buffalo id 2 serialized with the same fields and timestamps as Node, including
  `createdAt=2026-10-28T06:49:55.000Z` and `updatedAt=2026-10-28T07:03:25.000Z`.
- No live create/update/delete was executed.

---

## Phase 5 implementation

Created:

- `app/schemas/production.py` — Zod-compatible single/bulk payload validation, 2-decimal
  serializers, production detail include (`buffalo` + `recorder`), date/litres helpers.
- `app/repositories/production_repository.py` — duplicate lookup, daily list/details, buffalo
  history, grouped range totals, create/flush/commit/rollback.
- `app/repositories/buffalo_repository.py` — added `list_active()` sorted by `tag_no`.
- `app/services/production_service.py` — grid/list/summary/history and single/bulk writes,
  future/operator date rules, active-buffalo guard, duplicate `overwrite`, atomic bulk rollback.
- `app/routers/production.py` — `/api/v1/production/*` routes for admin + operator, query
  validation, single-vs-bulk dispatch, 201 responses.
- `app/core/dependencies.py`, `app/main.py` — production repository/service wiring and router.
- `tests/test_phase5.py` — schemas, service, API, transaction rollback, validation, and query tests.

Also corrected Phase 3/4 validation messages to the actual Node Zod 4 runtime messages. Zod 4
ignores `required_error`/`errorMap`; missing values and enum failures now use
`Invalid input: expected ...`, `Invalid option: expected one of ...`, and `Too small/Too big...`.

Contract details preserved:

- Grid is active buffaloes only, ordered `tag_no ASC`; herd totals sum present sessions; daily
  total is null when both sessions are null.
- Single/bulk date rules: future 400 `INVALID_PRODUCTION_DATE`; operator non-today 403
  `OPERATOR_DATE_RESTRICTION`.
- Missing/inactive buffalo: 404 / 400 `BUFFALO_NOT_ACTIVE` with exact Node messages.
- Duplicate active key: 409 `DUPLICATE_PRODUCTION_ENTRY`; `overwrite=true` updates litres and
  `recorded_by`.
- Bulk is atomic, supports morning/evening pairs and explicit session/litres, and rolls back on any
  conflict or guard failure.
- Summary/history aggregate per day; decimals and timestamps serialize exactly as Node.
- Soft-deleted production rows are excluded from reads but still occupy the DB unique key; a
  re-create collision maps to 409 `DUPLICATE_ENTRY`.

Verification:

- `uv run pytest -q` → **125 passed**, 8 subtests passed.
- `uv run ruff check app tests` → clean; compileall clean.
- Read-only live smoke: grid `2025-01-15` → 57 active, herd `16.50/15.00/31.50`, buffalo 63 row
  `6.50/5.50/12.00`; summary `2025-01-01..2025-01-20` → 1 day, total `31.50`; buffalo 63 history
  total `12.00`.
- Read-only API smoke through ASGI with live DB: grid/summary/history 200; missing `to` and invalid
  body 400 with expected envelopes.
- No live create/update/delete was executed.

---

## Exception handling refactor

The custom `AppError` hierarchy (`BadRequestError`, `UnauthorizedError`, `ForbiddenError`,
`NotFoundError`, `ConflictError`) was removed after Phase 5. Application code now raises
`fastapi.HTTPException` through `api_error(status_code, code, message)`, with
`detail={"code", "message"}`; route status codes use `fastapi.status` constants.

- The exception handlers still produce the Node envelope `{"error":{"code","message"}}`.
- Custom detail dictionaries are preserved for business 404s; only framework-generated 404/405
  responses use `Cannot {METHOD} {path}`.
- Validation remains 400 `VALIDATION_ERROR`, with the first issue rendered as
  `"{path}: {message}"`.
- Tests were migrated from class-based exception assertions to `HTTPException` and
  `detail["code"]`. This refactor made no API contract change.
- After the refactor: `uv run pytest -q` → **125 passed**, 8 subtests passed; ruff clean.

---

## Phase 6 implementation

Created:

- `app/schemas/wastage.py` — Zod-compatible wastage payload validation, query model, 2-decimal
  wastage serializer, and recorder include.
- `app/repositories/stock_repository.py` — before/current production/sales/wastage sums and future
  active-date discovery, all excluding soft-deleted rows.
- `app/repositories/wastage_repository.py` — create, filtered list/count with recorder join,
  DESC ordering, pagination, flush/commit/rollback.
- `app/services/stock_service.py` — derived opening/closing stock, stock history, and availability
  checks against the requested day and every later active date.
- `app/services/wastage_service.py` — date permissions, stock guard, atomic insert, remaining-stock
  response, filtered listing, and range validation.
- `app/routers/stock.py`, `app/routers/wastage.py` — `/api/v1/stock` and `/api/v1/wastage` routes
  for admin + operator, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` — repository/service wiring,
  router registration, and wastage field validation labels.
- `tests/test_phase6.py` — schemas, stock calculations/history, current/future stock guards,
  wastage permissions/transactions/listing, API responses, and validation messages.

Contract details preserved:

- Stock formula: `opening = prior production - prior sales - prior wastage`;
  `closing = opening + produced - sold - wasted`; all values are 2-decimal strings.
- `GET /stock` uses the business date when `date` is omitted. `GET /stock/history` requires
  `from` and `to`, returns `{period:{from,to},history[]}`, and rejects `from > to`.
- Wastage stock check rejects insufficient current stock with `Only {available} L available` and
  insufficient future margin with the exact Node message including date, requested litres, future
  date, and margin.
- Wastage dates: future 400 `INVALID_WASTAGE_DATE`; operator non-today 403
  `OPERATOR_DATE_RESTRICTION`; admin may write past dates subject to stock.
- Wastage reasons are `spoiled|spilled|returned`; litres must be positive; stored and returned with
  two decimals.
- Successful POST returns `201 {wastage, stock_remaining}`. Wastage JSON includes
  `id,waste_date,litres,reason,recorded_by,is_deleted,createdAt,updatedAt`; list items also include
  `recorder{id,full_name,username}`.
- Wastage list filters: exact `waste_date` overrides range filters; range applies only when both
  `from` and `to` are present; one-sided ranges are supported. Order is
  `waste_date DESC, created_at DESC`; pagination defaults 1/20, max 100.
- Insert + stock recomputation share one session; any failure rolls back. Availability remains
  unlocked read-then-write, matching Node (the concurrency decision is still open).
- Zod-compatible validation messages are preserved for body and query parameters, including
  `Invalid input`, `Invalid option`, `Too small/Too big`, and the default regex message.

Verification:

- `uv run pytest -q` → **139 passed**, 25 subtests passed.
- `uv run ruff check app tests` → clean; compileall clean.
- Read-only live service smoke matched Node exactly: `2026-10-29` stock
  `689.04/0.00/0.00/0.00/689.04`; history `2026-10-27..29` matched all 15 values; wastage total `5`
  with recorder joins.
- Read-only ASGI API smoke: stock, stock history, and wastage list all returned 200 with the same
  bodies as Node, including decimal strings and ISO timestamps.
- No live create/update/delete was executed.

---

## Phase 7 implementation

Created:

- `app/schemas/customer.py` — Zod-compatible create/update validation, query model, and customer
  serialization with 2-decimal rates and camel-case timestamps.
- `app/schemas/sale.py` — create/update validation, query model, sale/customer/recorder
  serialization for list (no customer address) and detail (customer address included).
- `app/repositories/customer_repository.py` — non-deleted lookup, filtered list/count ordered by
  name, create, and sales/invoice financial aggregation.
- `app/repositories/sale_repository.py` — non-deleted lookup with customer/recorder joins, filtered
  list/count, create, flush/commit/rollback.
- `app/services/customer_service.py` — list/get/create/update/balance, normalization, 404 messages.
- `app/services/sale_service.py` — date permissions, active-customer guard, captured/default rate,
  amount calculation, stock assertion, atomic create, filtered listing, and stock-aware update.
- `app/routers/customers.py`, `app/routers/sales.py` — `/api/v1/customers/*` and `/api/v1/sales/*`
  for admin + operator, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` — repository/service wiring,
  router registration, and numeric/date validation field mappings.
- `tests/test_phase7.py` — schemas, customer listing/create/update/balance, sale create/update/
  listing, permissions, inactive customer, stock guards, API envelopes, and validation messages.

Contract details preserved:

- Customer JSON: `id,name,phone,address,rate_per_litre,is_active,is_deleted,createdAt,updatedAt`.
  List ordering is `name ASC`; `search` trims and matches name/phone; `is_active` filters exactly.
- Customer create trims name/phone/address, stores empty phone/address as null, and defaults
  `is_active` to true. Update is partial; explicit null clears phone/address.
- Balance returns `customer_id,customer_name,rate_per_litre,is_active,total_sales_amount,
  total_paid_amount,outstanding_balance`; totals exclude soft-deleted sales/invoices and outstanding
  is floored at zero.
- `POST /sales` returns the flat sale fields plus `stock_remaining` (no `{sale}` wrapper). List
  returns `{items,page,page_size,total}`; get/update return `{sale}`.
- Sale list customers omit `address`; sale detail customers include it. Both include
  `recorder{id,full_name,username}`.
- Sale create captures the supplied rate or the customer's current rate, computes
  `round(litres*rate, 2)`, stores `unpaid`, and checks stock before insert.
- Sale update recalculates amount and sets `recorded_by`; stock is re-checked when litres increase
  or the date changes, matching Node.
- Date rules: future 400 `INVALID_SALE_DATE`; operator non-today 403
  `OPERATOR_DATE_RESTRICTION`; missing customer 404; inactive customer 400
  `CUSTOMER_NOT_ACTIVE`. Sale list rejects `from > to` with 400 `INVALID_DATE_RANGE` unless an
  exact `sale_date` is present.
- List filters combine `customer_id`, exact `sale_date` or range, and `payment_status`; ordering is
  `sale_date DESC, created_at DESC`; pagination defaults 1/20, max 100.

Verification:

- `uv run pytest -q` → **154 passed**, 48 subtests passed.
- `uv run ruff check app tests` → clean; compileall clean.
- Read-only live service/Node comparison matched exactly: customer page 1 (`total=69`), customer 40
  balance, sales page 1 (`total=64`), and sale 67 detail including customer address and recorder.
- No live create/update/delete was executed.

---

## Phase 8 implementation

Created:

- `app/models/invoice.py`, `app/models/invoice_sale.py` — invoice and link models matching the live
  schema (unique `invoice_no`, unique `sale_id`, composite `(invoice_id, sale_id)`).
- `app/schemas/invoice.py` — create/payment validation, query model, and invoice/customer/sale
  serialization with `balance`.
- `app/repositories/invoice_repository.py` — detail lookup with joins, filtered list/count,
  invoice-number lookup, link creation, and linked-sale payment updates.
- `app/services/invoice_service.py` — number generation, explicit/period sale selection, duplicate
  and invalid-sale guards, payment tracking, and PDF generation.
- `app/utils/pdf.py` — ReportLab invoice PDF (header, customer card, line items, totals).
- `app/routers/invoices.py` — `/api/v1/invoices*` for admin + operator.
- `tests/test_phase8.py` — schemas, service flows, API envelopes, PDF headers, and query messages.

Contract details preserved:

- Invoice JSON includes `id,invoice_no,customer_id,period_start,period_end,total_amount,
  paid_amount,status,is_deleted,createdAt,updatedAt,customer,balance`; detail adds `sales[]`.
- List customers expose `id,name,phone,is_active`; detail adds `address,rate_per_litre`.
- `total_pages` is added to the list envelope; ordering is `created_at DESC`.
- Payment adds to `paid_amount`, derives `unpaid/partial/paid`, and marks linked sales `paid` when
  the invoice is fully paid. Overpayment is preserved, matching Node.
- `GET /invoices/:id/pdf` returns `application/pdf` with
  `Content-Disposition: inline; filename="invoice-<no>.pdf"`.

Verification:

- `uv run pytest -q` → **163 passed**, 68 subtests passed.
- `uv run ruff check app tests` → clean.
- Read-only live smoke: list/detail/PDF for existing invoices matched Node byte-comparable values.

---

## Phase 9 implementation

Created:

- `app/schemas/expense_category.py` — create validation (trim, lowercase, 2–80 chars) and category
  serialization with camel-case timestamps.
- `app/schemas/expense.py` — create/update validation (`UNSET` sentinel so `note: null` clears),
  query model, and expense serialization with `category{id,name}` and `recorder{...}`.
- `app/repositories/expense_category_repository.py` — active list ordered by name, id/name lookup,
  create.
- `app/repositories/expense_repository.py` — detail lookup with category/recorder joins, filtered
  list/count plus summed amount, create, attribute updates.
- `app/services/expense_category_service.py` — list and create with `DUPLICATE_CATEGORY` (409).
- `app/services/expense_service.py` — list/get/create/update with category existence checks,
  2-decimal amounts, `note` trimming/null handling, and `total_pages`/`total_expense_amount`.
- `app/routers/expenses.py` — admin-only `/api/v1/expenses*` and the `/api/v1/expense-categories`
  alias, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` — repository/service wiring,
  router registration, and expense field validation mappings.
- `tests/test_phase9.py` — schemas, category/expense services, admin-only enforcement, envelopes,
  and validation messages.

Contract details preserved:

- Both routers are admin-only; operators get 403
  `Access denied: Requires one of [admin] role`.
- `GET /expenses/categories` and `GET /expense-categories` both return `{categories}` ordered by
  name; category JSON is `id,name,is_deleted,createdAt,updatedAt`.
- `POST /expenses/categories` returns `201 {category}`; names are trimmed and lowercased, and a
  duplicate active name returns 409 `DUPLICATE_CATEGORY` with
  `Expense category 'x' already exists`.
- `GET /expenses` returns `{items,page,page_size,total,total_pages,total_expense_amount}`; ordering
  is `expense_date DESC, created_at DESC`; `category_id` filters exactly and `from`/`to` are applied
  only when both are present, matching the Node service.
- `POST /expenses` returns `201 {expense}` and requires an existing, non-deleted category (404
  `Expense category with id N not found`); amounts are stored and returned with two decimals.
- `PUT /expenses/:id` supports partial updates, re-validates the category, and allows clearing
  `note` with `null`.
- Missing or soft-deleted expenses return 404 `Expense with id N not found`.
- Preserved Node quirk: no `from <= to` validation on the expense list (documented open decision).

Verification:

- `uv run pytest -q` → **176 passed**, 88 subtests passed (163 before this phase; 13 new).
- `uv run ruff check app tests` → `All checks passed!`
- `uv run python -m compileall -q app tests` → clean.
- No live write path was exercised; the live expense list/get endpoints have not been compared against
  Node yet.

---

## Phase 10 implementation

Created:

- `app/schemas/report.py` — profit/production/dashboard query models plus shared date and month
  patterns.
- `app/repositories/report_repository.py` — sales rows in range, expense rows with category names,
  daily sales totals, sales/expense amount totals, and per-session production totals for a date.
- `app/services/report_service.py` — profit report, production report delegation, dashboard
  snapshot, and date-range resolution.
- `app/routers/reports.py` — `/api/v1/reports/profit` (admin), `/reports/production` and
  `/reports/dashboard` (admin + operator).
- `app/core/dependencies.py`, `app/main.py` — report repository/service wiring and router
  registration.
- `tests/test_phase10.py` — date-range rules, profit aggregation, production delegation, dashboard
  role behaviour, API envelopes, and validation messages.

Contract details preserved:

- Range precedence is `date` > `month` > `from`/`to` > current business month; `period` is validated
  (`daily|monthly|custom`) but ignored, as in Node.
- `from > to` returns 400 `INVALID_DATE_RANGE`, `'from' date cannot be after 'to' date`. A one-sided
  range falls back to the current month, matching Node.
- Profit response is `{period,summary,category_breakdown,daily_breakdown}`; daily rows are ordered by
  date ascending with `revenue/expenses/profit/litres_sold` as 2-decimal strings, and categories
  carry `total_amount` plus a one-decimal `percentage` (uncategorized expenses group under
  `uncategorized`).
- Production report reuses the Phase 5 summary; missing `from`/`to` returns an empty summary rather
  than raising (Node's schema allows omission but its query is undefined there — documented
  deviation).
- Dashboard returns `{date,buffaloes,production,stock,sales,financials}`; `financials` is `null` for
  operators, and admin financials cover today plus month-to-date from the 1st of the month.
- Date/month query values must match the Node regex and be real calendar values; impossible dates
  return the same 400 validation message instead of a 500.

Verification:

- `uv run pytest -q` → **197 passed**, 94 subtests passed (176 before this phase; 21 new).
- `uv run ruff check app tests` → `All checks passed!`
- `uv run python -m compileall -q app tests` → clean.
- No live endpoint comparison against Node for reports yet.

---

## Phase 11 implementation

Created:

- `app/seeders/store.py` — `SeedStore`, the small persistence surface (`find`, `find_all`, `create`,
  `flush`, `commit`, `rollback`) used by the seeders. Lookups ignore `is_deleted`, matching Node's
  `findOrCreate` on the natural key.
- `app/seeders/base_seed.py` — idempotent base seed: the six PRD expense categories and the initial
  admin user from `ADMIN_*` settings (bcrypt cost 10).
- `app/seeders/fake_indian_data.py` — Faker (`en_IN`) fake farm data: 3 operators, 12 buffaloes with
  Murrah/Surti/... breeds and 9 active statuses, 8 customers (1 inactive), 6 days x 2 sessions of
  production for active buffaloes, one spilled wastage, 4 days of sales for the first 4 active
  customers, one partially paid invoice with sale links, and one expense per category.
- `tests/test_phase11.py` — runs both seeders against an in-memory store (no database contact),
  covering row counts, values, invoice totals/links, and repeat-run behaviour.

Contract details preserved:

- Natural keys mirror Node: category by name, user by email, buffalo by tag, production by
  `(buffalo_id, prod_date, session)`, wastage by `(waste_date, reason)`, sale by
  `(customer_id, sale_date, litres)`, invoice by `invoice_no`, invoice link by `sale_id`, expense by
  `(category_id, expense_date, amount)`.
- Operator password is `Operator@123`; operators are `ramesh_operator`, `suresh_operator`,
  `priya_operator` with the same emails as Node.
- Buffalo tags are `TAG-0101`..`TAG-0112`; statuses are 9 active, 1 dry, 1 sold, 1 dead; customer
  rates step from 60.00 to 70.00 and the 8th customer is inactive.
- Invoice number is `INV-YYYYMM-0001`, status `partial`, paid amount is half of the linked sales.
- Because sale and expense natural keys include random amounts, re-running adds new sale/expense
  rows while everything else stays idempotent — the same behaviour as Node.
- Only one intentional deviation: business dates come from `Asia/Kolkata` (`get_business_date`)
  rather than the Node script's UTC `toISOString()`.

Faker compatibility:

- The seeder accepts either the modern Faker API (`person.full_name()`, `phone_number()`) or the
  legacy one (`name()`, `phone()`, `address()`), because the environment's installed Faker does not
  expose `person` even though `uv.lock` pins 40.43.0. `tests/test_phase11.py` covers both shapes.
- `app/seeders/__init__.py` no longer re-exports the modules, which removes the
  `runpy` "found in sys.modules" warning when running the seeders with `python -m`.

Verification:

- `uv run pytest -q` → **210 passed**, 94 subtests passed (197 before this phase; 13 new).
- `uv run ruff check app tests` → `All checks passed!`
- `uv run python -m compileall -q app tests` → clean.
- Live attempts (user-run): `python -m app.seeders.base_seed` connected read/write and reported no
  changes (all six categories and the admin email already existed). `python -m
  app.seeders.fake_indian_data` failed on the Faker `person` provider before any commit; the seeder
  rolled the transaction back, so no fake rows were persisted. The fake seeder has not yet completed
  a successful live run.

---

## Swagger authorization fix

`get_current_user` read the raw `Authorization` header, so FastAPI never registered a security
scheme and Swagger UI had no **Authorize** button. It now also declares
`Security(HTTPBearer(auto_error=False, scheme_name="BearerAuth"))`, which adds the http/bearer scheme
to the OpenAPI document and a padlock to every protected operation without changing any error
behaviour (the header checks still run first, so the Node 401 messages are unchanged).
`tests/test_phase1.py::test_openapi_documents_bearer_auth` asserts the scheme exists, that
`GET /api/v1/customers` requires it, and that `/health` stays public.

---

## Key facts locked in

- MySQL is the target database (port 3307, DB name from env; values not printed).
- Existing tables are created by `sequelize.sync({ force: false })`, not Prisma.
- API prefix `/api/v1`; health also at `/health`.
- JWT payload `{id,email,username,role,iat,exp}`, HS256, expiry default 480 minutes.
- Error envelope `{"error":{"code","message"}}`; Zod validation becomes 400 `VALIDATION_ERROR`,
  not FastAPI's default 422.
- Dates use `Asia/Kolkata`; decimals must serialize as 2-decimal strings.
- Pagination default 20, max 100.
- Response envelopes vary per route; see `API_PARITY.md`.
- User timestamps: login/list/create/update/status return `createdAt`/`updatedAt`; `/auth/me`
  returns `created_at`/`updated_at`.
- Soft delete via `is_deleted`; no global ORM filter. Generic delete never cascades.
- Buffalo dates serialize as `YYYY-MM-DD` or null; buffalo timestamps are camel-case.

---

## Decisions required before later phases

1. Concurrency: preserve Node's unlocked read-then-write, or add MySQL `GET_LOCK` serialization.
2. Soft-deleted unique rows: restore/overwrite on re-entry, or return conflict.
3. Payments: preserve Node overpayment + sale status behavior, or align to ADR-004.
4. Operator rights: allow sales/invoice edits (Node) or restrict to create/view/print (PRD §4).
5. Scope: include password reset, customer sales history, CSV/PDF report exports (missing in Node)?
6. [x] JWT confirmed as `{id,email,username,role}` plus `iat`/`exp` (no `sub`).
7. [x] Read-only live MySQL schema inspection approved and completed.
8. [x] `pytest` and `ruff` installed; `pytest-asyncio`/`pytest-cov` not needed (stdlib async tests).
9. [x] Driver: async SQLAlchemy with installed `asyncmy`.
10. [x] `alembic stamp head` executed on the live DB; only `alembic_version` was written.

---

## Environment

- OS: Windows 11; shell: PowerShell (earlier phases used `cmd.exe`).
- The agent command runner requires Git Bash, which is currently missing; either install Git for
  Windows or set `CODEBUFF_GIT_BASH_PATH` to `bash.exe` so the agent can run the checks itself.
- Python: 3.11.15 in `backend_py/.venv`; `uv` 0.13.5.
- `backend_py` has its own nested `.git`.
- `pytest` 9.2.0 and `ruff` 0.17.3 installed; `pytest-asyncio`/`pytest-cov` are not installed and
  are not required by the stdlib async tests.
- Missing sync MySQL driver: `pymysql`/`mysqlclient`.
- `backend_py/.env.example` exists; no real `.env` yet.
- `greenlet` 3.5.6 installed; `faker` and `tzdata` declared and present.
- Alembic configured (`alembic.ini`, async `env.py`); baseline `0001_baseline` exists.
- Live DB `alembic_version` contains `0001_baseline`; 11 tables total.
- `backend_py/.env` remains absent; live commands read credentials from the environment or the
  backend's existing configuration.

---

## Phase 12 — parity audit and handoff

Created:

- `HANDOFF.md` — how to run, verify, and seed the backend; the full endpoint/role matrix; deliberate
  deviations from Node; open decisions; and what was not done.
- `API_PARITY.md` header now states that all 51 audited endpoints are implemented (Phases 1–10).

Audit result: every route in `backend/src/routes` has a Python counterpart with the same path, verb,
role guard, envelope, and error codes. Test coverage per phase:

| Phase | Tests added |
| --- | --- |
| 1–3 | 72 |
| 4 | 31 |
| 5 | 22 |
| 6 | 14 |
| 7 | 15 |
| 8 | 9 |
| 9 | 13 |
| 10 | 21 |
| 11 | 13 |

Final state: **210 passed**, 94 subtests, `ruff` clean, `compileall` clean.

## Next step

1. Optional: run the fake seeder against MySQL (`uv run python -m app.seeders.fake_indian_data`) to
   populate demo data; it writes rows and needs approval.
2. Optional: live side-by-side comparison of the Phase 9–11 endpoints and reports against Node.
3. Outstanding product decisions are listed in `HANDOFF.md` §6.

No further live DDL, migration, or seed will run without separate approval.
