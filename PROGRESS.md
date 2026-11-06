# Progress â€” Python/FastAPI Migration

**Current phase:** Phase 15 complete â€” session revocation + background email
**Last updated:** 2026-10-31
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
| 13 | Feature fixes: operator deletion, report PDFs, invoice PDF | **COMPLETE** |
| 14 | Security hardening + password reset | **COMPLETE** |
| 15 | Session revocation + background email | **COMPLETE** |

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

- `MIGRATION_PLAN.md` â€” structure, modules, endpoints, dependencies, PRD matrix, risks, order, Alembic strategy, seed plan.
- `API_PARITY.md` â€” 51 endpoints with auth, request/response envelopes, errors, test plan.
- `SCHEMA_MAPPING.md` â€” 10 tables, exact columns/types/constraints/indexes/FKs, baseline procedure.
- `PROGRESS.md` â€” this file.

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

- `app/core/config.py` â€” pydantic-settings, env aliases, masked secrets, async MySQL URL builder.
- `app/core/errors.py` â€” Node-compatible error envelope, 400 validation / 404 / 405 / 500 handlers.
- `app/core/middleware.py` â€” 1 MB body limit, Helmet-style headers, request logging.
- `app/core/logging.py` â€” root logging setup.
- `app/db/session.py` â€” async engine, session factory, DB health probe, dispose.
- `app/db/base.py` â€” declarative base for Phase 2 models.
- `app/routers/health.py` â€” `/health` + `/api/v1/health`.
- `app/routers/docs.py` â€” Swagger UI at `/docs` and `/api/v1/docs`.
- `app/main.py` â€” app factory, CORS, middleware order, OpenAPI at `/api/v1/docs/openapi.json`.
- `app/schemas/health.py`, `app/utils/time.py`.
- `.env.example` (placeholders only, no real secrets).
- `tests/test_health_and_docs.py`, `tests/test_middleware.py`, `tests/test_time.py` â€”
  stdlib `unittest` + `httpx` smoke tests (no live DB).

Dependencies:

- Installed `greenlet==3.5.6` (approved) and declared it, plus `faker` and `tzdata`, in `pyproject.toml`.
- Set `[tool.uv] package = false`; removed the broken `backend-py = "backend_py:main"` script.
- `uv lock` updated; `uv sync --check` reports no changes.

Verification:

- `uv run python -m unittest discover -s tests -v` â†’ **11 tests passed**.
- `uv run python -m compileall -q app tests` â†’ passed.
- Confirmed: `/health` and `/api/v1/health`; `/docs` and `/api/v1/docs`; generated OpenAPI at
  `/api/v1/docs/openapi.json`; 404/405 envelope; CORS preflight with credentials; security headers;
  1 MB body limit â†’ 413; Asia/Kolkata business-date boundary.
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

- `app/models/` â€” 10 SQLAlchemy 2.x models with exact live type, nullability, server defaults,
  index names, FK names/rules, engine, charset, and collation.
- `app/models/base.py` â€” `TimestampMixin`, `SoftDeleteMixin`, and timezone-naive timestamp helper.
- `alembic.ini` â€” no embedded URL; imports `settings` from `%(here)s`.
- `alembic/env.py` â€” async engine from `settings.sqlalchemy_database_url`, `Base.metadata` target.
- `alembic/script.py.mako`, `alembic/versions/0001_baseline_existing_schema.py` â€” empty baseline.
- `tests/test_models.py` â€” 12 no-DB tests for tables, indexes, cascades, decimals, timestamps,
  collation, and normalizers.

Verification:

- Metadata comparator vs live snapshot: **MATCH** (10 tables, columns, types, nullability,
  defaults, indexes, FKs, engine, collation).
- `uv run python -m unittest discover -s tests -v` â†’ **23 tests passed**.
- `uv run python -m compileall -q app tests alembic` â†’ passed.
- `alembic history` / `heads` â†’ `0001_baseline (head)`.
- `alembic upgrade head --sql` â†’ only `CREATE TABLE alembic_version` + baseline INSERT; no
  application DDL. Offline SQL generation opened no DB connection.
- `alembic stamp head` approved and executed â†’ `alembic_version = 0001_baseline`.
- Post-stamp read-only check â†’ 11 tables: the original 10 plus `alembic_version`; no application
  table was created, altered, or dropped.

Not performed:

- No application DDL, Alembic `upgrade`, or seed against MySQL.
- No live ORM writes; Phases 3â€“4 performed read-only list/get/count queries against the live
  `users` and `buffaloes` tables.
- No `backend_py/.env` was created; live commands read credentials transiently from the existing
  backend configuration without printing them.

---

## Phase 3 implementation

Created:

- `app/core/security.py` â€” bcrypt cost 10 with 72-byte truncation; HS256 JWT with
  `{id,email,username,role,iat,exp}`.
- `app/core/dependencies.py` â€” Bearer authentication, DB reload, deleted/inactive rejection,
  `require_roles`/`require_admin`, repository/service dependencies.
- `app/schemas/user.py` â€” login/create/update/status request validation, query parsing model,
  Node-compatible user serialization.
- `app/repositories/user_repository.py` â€” async user lookup, list/count, create, commit helpers.
- `app/services/auth_service.py` â€” login, generic credential errors, inactive check, `/auth/me`.
- `app/services/user_service.py` â€” admin list/create/get/update/status, duplicate checks,
  self-deactivation guard, normalized email/username, hashed passwords.
- `app/routers/auth.py`, `app/routers/users.py` â€” `/api/v1/auth/*` and admin-only `/api/v1/users`.
- `tests/test_auth_and_users.py` â€” security, serialization, service, and API tests with fake repository/DB.
- `pyproject.toml` â€” installed `pytest`, `ruff`; added a conservative ruff config.

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

- `uv run pytest -q` â†’ **72 passed** (including 23 prior tests).
- `uv run ruff check app tests` â†’ clean.
- Read-only live smoke test: list users (`total=13`), email lookup, `/auth/me` shape, and service
  serialization succeeded; id 1 timestamp `2026-10-28 12:10:23` serialized to
  `2026-10-28T06:40:23.000Z`, matching Node.
- No live create/update/delete was executed.

---

## Phase 4 implementation

Created:

- `app/schemas/buffalo.py` â€” create/update validation, query model, exact errors, buffalo
  serialization with camel-case timestamps.
- `app/repositories/buffalo_repository.py` â€” non-deleted lookup, tag lookup, filtered list/count,
  status counts, create/commit helpers.
- `app/repositories/delete_repository.py` â€” generic soft delete by model and ID.
- `app/services/buffalo_service.py` â€” list/get/create/update/counts, tag normalization,
  duplicate messages, date conversion.
- `app/services/delete_service.py` â€” allowlist, admin soft delete, Node-compatible response and
  not-found messages.
- `app/routers/buffaloes.py`, `app/routers/delete.py` â€” `/api/v1/buffaloes/*` for admin+operator
  and admin-only `DELETE /api/v1/{resource}/{id}`.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py`, `app/utils/time.py` â€” wiring,
  validation labels, shared timestamp helper.
- `tests/test_buffaloes_and_soft_delete.py` â€” serialization, validation, service, delete, and API tests with fakes.

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

- `uv run pytest -q` â†’ **103 passed**.
- `uv run ruff check app tests` â†’ clean; compileall clean.
- Read-only live smoke test: `total=65`, counts `{active:57,dry:1,sold:6,dead:1}` matched Node
  exactly; buffalo id 2 serialized with the same fields and timestamps as Node, including
  `createdAt=2026-10-28T06:49:55.000Z` and `updatedAt=2026-10-28T07:03:25.000Z`.
- No live create/update/delete was executed.

---

## Phase 5 implementation

Created:

- `app/schemas/production.py` â€” Zod-compatible single/bulk payload validation, 2-decimal
  serializers, production detail include (`buffalo` + `recorder`), date/litres helpers.
- `app/repositories/production_repository.py` â€” duplicate lookup, daily list/details, buffalo
  history, grouped range totals, create/flush/commit/rollback.
- `app/repositories/buffalo_repository.py` â€” added `list_active()` sorted by `tag_no`.
- `app/services/production_service.py` â€” grid/list/summary/history and single/bulk writes,
  future/operator date rules, active-buffalo guard, duplicate `overwrite`, atomic bulk rollback.
- `app/routers/production.py` â€” `/api/v1/production/*` routes for admin + operator, query
  validation, single-vs-bulk dispatch, 201 responses.
- `app/core/dependencies.py`, `app/main.py` â€” production repository/service wiring and router.
- `tests/test_production.py` â€” schemas, service, API, transaction rollback, validation, and query tests.

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

- `uv run pytest -q` â†’ **125 passed**, 8 subtests passed.
- `uv run ruff check app tests` â†’ clean; compileall clean.
- Read-only live smoke: grid `2025-01-15` â†’ 57 active, herd `16.50/15.00/31.50`, buffalo 63 row
  `6.50/5.50/12.00`; summary `2025-01-01..2025-01-20` â†’ 1 day, total `31.50`; buffalo 63 history
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
- After the refactor: `uv run pytest -q` â†’ **125 passed**, 8 subtests passed; ruff clean.

---

## Phase 6 implementation

Created:

- `app/schemas/wastage.py` â€” Zod-compatible wastage payload validation, query model, 2-decimal
  wastage serializer, and recorder include.
- `app/repositories/stock_repository.py` â€” before/current production/sales/wastage sums and future
  active-date discovery, all excluding soft-deleted rows.
- `app/repositories/wastage_repository.py` â€” create, filtered list/count with recorder join,
  DESC ordering, pagination, flush/commit/rollback.
- `app/services/stock_service.py` â€” derived opening/closing stock, stock history, and availability
  checks against the requested day and every later active date.
- `app/services/wastage_service.py` â€” date permissions, stock guard, atomic insert, remaining-stock
  response, filtered listing, and range validation.
- `app/routers/stock.py`, `app/routers/wastage.py` â€” `/api/v1/stock` and `/api/v1/wastage` routes
  for admin + operator, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` â€” repository/service wiring,
  router registration, and wastage field validation labels.
- `tests/test_stock_and_wastage.py` â€” schemas, stock calculations/history, current/future stock guards,
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

- `uv run pytest -q` â†’ **139 passed**, 25 subtests passed.
- `uv run ruff check app tests` â†’ clean; compileall clean.
- Read-only live service smoke matched Node exactly: `2026-10-29` stock
  `689.04/0.00/0.00/0.00/689.04`; history `2026-10-27..29` matched all 15 values; wastage total `5`
  with recorder joins.
- Read-only ASGI API smoke: stock, stock history, and wastage list all returned 200 with the same
  bodies as Node, including decimal strings and ISO timestamps.
- No live create/update/delete was executed.

---

## Phase 7 implementation

Created:

- `app/schemas/customer.py` â€” Zod-compatible create/update validation, query model, and customer
  serialization with 2-decimal rates and camel-case timestamps.
- `app/schemas/sale.py` â€” create/update validation, query model, sale/customer/recorder
  serialization for list (no customer address) and detail (customer address included).
- `app/repositories/customer_repository.py` â€” non-deleted lookup, filtered list/count ordered by
  name, create, and sales/invoice financial aggregation.
- `app/repositories/sale_repository.py` â€” non-deleted lookup with customer/recorder joins, filtered
  list/count, create, flush/commit/rollback.
- `app/services/customer_service.py` â€” list/get/create/update/balance, normalization, 404 messages.
- `app/services/sale_service.py` â€” date permissions, active-customer guard, captured/default rate,
  amount calculation, stock assertion, atomic create, filtered listing, and stock-aware update.
- `app/routers/customers.py`, `app/routers/sales.py` â€” `/api/v1/customers/*` and `/api/v1/sales/*`
  for admin + operator, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` â€” repository/service wiring,
  router registration, and numeric/date validation field mappings.
- `tests/test_customers_and_sales.py` â€” schemas, customer listing/create/update/balance, sale create/update/
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

- `uv run pytest -q` â†’ **154 passed**, 48 subtests passed.
- `uv run ruff check app tests` â†’ clean; compileall clean.
- Read-only live service/Node comparison matched exactly: customer page 1 (`total=69`), customer 40
  balance, sales page 1 (`total=64`), and sale 67 detail including customer address and recorder.
- No live create/update/delete was executed.

---

## Phase 8 implementation

Created:

- `app/models/invoice.py`, `app/models/invoice_sale.py` â€” invoice and link models matching the live
  schema (unique `invoice_no`, unique `sale_id`, composite `(invoice_id, sale_id)`).
- `app/schemas/invoice.py` â€” create/payment validation, query model, and invoice/customer/sale
  serialization with `balance`.
- `app/repositories/invoice_repository.py` â€” detail lookup with joins, filtered list/count,
  invoice-number lookup, link creation, and linked-sale payment updates.
- `app/services/invoice_service.py` â€” number generation, explicit/period sale selection, duplicate
  and invalid-sale guards, payment tracking, and PDF generation.
- `app/utils/pdf.py` â€” ReportLab invoice PDF (header, customer card, line items, totals).
- `app/routers/invoices.py` â€” `/api/v1/invoices*` for admin + operator.
- `tests/test_invoices.py` â€” schemas, service flows, API envelopes, PDF headers, and query messages.

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

- `uv run pytest -q` â†’ **163 passed**, 68 subtests passed.
- `uv run ruff check app tests` â†’ clean.
- Read-only live smoke: list/detail/PDF for existing invoices matched Node byte-comparable values.

---

## Phase 9 implementation

Created:

- `app/schemas/expense_category.py` â€” create validation (trim, lowercase, 2â€“80 chars) and category
  serialization with camel-case timestamps.
- `app/schemas/expense.py` â€” create/update validation (`UNSET` sentinel so `note: null` clears),
  query model, and expense serialization with `category{id,name}` and `recorder{...}`.
- `app/repositories/expense_category_repository.py` â€” active list ordered by name, id/name lookup,
  create.
- `app/repositories/expense_repository.py` â€” detail lookup with category/recorder joins, filtered
  list/count plus summed amount, create, attribute updates.
- `app/services/expense_category_service.py` â€” list and create with `DUPLICATE_CATEGORY` (409).
- `app/services/expense_service.py` â€” list/get/create/update with category existence checks,
  2-decimal amounts, `note` trimming/null handling, and `total_pages`/`total_expense_amount`.
- `app/routers/expenses.py` â€” admin-only `/api/v1/expenses*` and the `/api/v1/expense-categories`
  alias, with Node-compatible query/body validation.
- `app/core/dependencies.py`, `app/main.py`, `app/core/errors.py` â€” repository/service wiring,
  router registration, and expense field validation mappings.
- `tests/test_expenses.py` â€” schemas, category/expense services, admin-only enforcement, envelopes,
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

- `uv run pytest -q` â†’ **176 passed**, 88 subtests passed (163 before this phase; 13 new).
- `uv run ruff check app tests` â†’ `All checks passed!`
- `uv run python -m compileall -q app tests` â†’ clean.
- No live write path was exercised; the live expense list/get endpoints have not been compared against
  Node yet.

---

## Phase 10 implementation

Created:

- `app/schemas/report.py` â€” profit/production/dashboard query models plus shared date and month
  patterns.
- `app/repositories/report_repository.py` â€” sales rows in range, expense rows with category names,
  daily sales totals, sales/expense amount totals, and per-session production totals for a date.
- `app/services/report_service.py` â€” profit report, production report delegation, dashboard
  snapshot, and date-range resolution.
- `app/routers/reports.py` â€” `/api/v1/reports/profit` (admin), `/reports/production` and
  `/reports/dashboard` (admin + operator).
- `app/core/dependencies.py`, `app/main.py` â€” report repository/service wiring and router
  registration.
- `tests/test_reports.py` â€” date-range rules, profit aggregation, production delegation, dashboard
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
  than raising (Node's schema allows omission but its query is undefined there â€” documented
  deviation).
- Dashboard returns `{date,buffaloes,production,stock,sales,financials}`; `financials` is `null` for
  operators, and admin financials cover today plus month-to-date from the 1st of the month.
- Date/month query values must match the Node regex and be real calendar values; impossible dates
  return the same 400 validation message instead of a 500.

Verification:

- `uv run pytest -q` â†’ **197 passed**, 94 subtests passed (176 before this phase; 21 new).
- `uv run ruff check app tests` â†’ `All checks passed!`
- `uv run python -m compileall -q app tests` â†’ clean.
- No live endpoint comparison against Node for reports yet.

---

## Phase 11 implementation

Created:

- `app/seeders/store.py` â€” `SeedStore`, the small persistence surface (`find`, `find_all`, `create`,
  `flush`, `commit`, `rollback`) used by the seeders. Lookups ignore `is_deleted`, matching Node's
  `findOrCreate` on the natural key.
- `app/seeders/base_seed.py` â€” idempotent base seed: the six PRD expense categories and the initial
  admin user from `ADMIN_*` settings (bcrypt cost 10).
- `app/seeders/fake_indian_data.py` â€” Faker (`en_IN`) fake farm data: 3 operators, 12 buffaloes with
  Murrah/Surti/... breeds and 9 active statuses, 8 customers (1 inactive), 6 days x 2 sessions of
  production for active buffaloes, one spilled wastage, 4 days of sales for the first 4 active
  customers, one partially paid invoice with sale links, and one expense per category.
- `tests/test_seeders.py` â€” runs both seeders against an in-memory store (no database contact),
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
  rows while everything else stays idempotent â€” the same behaviour as Node.
- Only one intentional deviation: business dates come from `Asia/Kolkata` (`get_business_date`)
  rather than the Node script's UTC `toISOString()`.

Faker compatibility:

- The seeder accepts either the modern Faker API (`person.full_name()`, `phone_number()`) or the
  legacy one (`name()`, `phone()`, `address()`), because the environment's installed Faker does not
  expose `person` even though `uv.lock` pins 40.43.0. `tests/test_seeders.py` covers both shapes.
- `app/seeders/__init__.py` no longer re-exports the modules, which removes the
  `runpy` "found in sys.modules" warning when running the seeders with `python -m`.

Verification:

- `uv run pytest -q` â†’ **210 passed**, 94 subtests passed (197 before this phase; 13 new).
- `uv run ruff check app tests` â†’ `All checks passed!`
- `uv run python -m compileall -q app tests` â†’ clean.
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
`tests/test_health_and_docs.py::test_openapi_documents_bearer_auth` asserts the scheme exists, that
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
4. Operator rights: allow sales/invoice edits (Node) or restrict to create/view/print (PRD Â§4).
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

## Phase 12 â€” parity audit and handoff

Created:

- `HANDOFF.md` â€” how to run, verify, and seed the backend; the full endpoint/role matrix; deliberate
  deviations from Node; open decisions; and what was not done.
- `API_PARITY.md` header now states that all 51 audited endpoints are implemented (Phases 1â€“10).

Audit result: every route in `backend/src/routes` has a Python counterpart with the same path, verb,
role guard, envelope, and error codes. Test coverage per phase:

| Phase | Tests added |
| --- | --- |
| 1â€“3 | 72 |
| 4 | 31 |
| 5 | 22 |
| 6 | 14 |
| 7 | 15 |
| 8 | 9 |
| 9 | 13 |
| 10 | 21 |
| 11 | 13 |

Final state: **210 passed**, 94 subtests, `ruff` clean, `compileall` clean.

## Phase 13 â€” feature fixes (operator deletion, report PDFs, invoice PDF)

Plan and progress: `../docs/FEATURE_FIX_PLAN.md`, `../docs/FEATURE_FIX_PROGRESS.md`.

Created/changed:

- `app/services/user_service.py` â€” `delete_user`: soft deletes operator accounts only
  (`is_deleted=true`, `is_active=false`), 400 for self-deletion, 400 for admin targets, 404 for
  missing/non-numeric/already-deleted ids.
- `app/routers/users.py` â€” `DELETE /users/{user_id}` behind the router's `require_admin` guard,
  registered before the generic `DELETE /{resource}/{id}` route.
- `app/schemas/report.py` â€” `REPORT_TYPES`, `REPORT_TYPE_LABELS`, `ReportExportQuery`.
- `app/utils/report_pdf.py` (new) â€” ReportLab platypus report builder: KPI strip, executive
  summary, A4 tables with repeating headers, vector charts (`reportlab.graphics`), 12-bar bucket
  cap, "Page X of Y" footer and an explicit no-data block.
- `app/services/report_service.py` â€” `generate_report_pdf` reusing the JSON report methods so the
  PDF and API figures cannot diverge; `dairy-<type>-report-<range>.pdf` filenames.
- `app/routers/reports.py` â€” `GET /reports/pdf` with `type=profit|production|dashboard`, admin-only
  profit, `application/pdf` + `attachment` + `no-store`, project 400 validation envelopes.
- `app/utils/pdf.py` â€” invoice rewritten on platypus: no invented business/tax details, wrapped
  descriptions, repeating table header, right-aligned totals block with balance due, payment status,
  page numbers, `Decimal`/`ROUND_HALF_UP` money.
- `tests/test_auth_and_users.py`, `tests/test_invoices.py`, `tests/test_reports.py` â€” new regression tests.

Python-only additions (Node has neither): `DELETE /users/:id`, `GET /reports/pdf`. Documented in
`API_PARITY.md`. No schema, dependency or lockfile change.

Verification: **357 passed**, 150 subtests, `ruff` clean (2026-10-30 full-suite run by the user).

## Phase 14 â€” security hardening and password reset

Changed:

- `app/core/middleware.py` â€” request logging redacts the values of `token`, `secret`,
  `password`, `api_key`/`apikey` query parameters; the 413 body-limit response uses the project
  envelope with `PAYLOAD_TOO_LARGE`.
- `app/core/errors.py` â€” 413 maps to `PAYLOAD_TOO_LARGE`, 429 to `RATE_LIMITED`.
- `app/core/config.py` â€” production-only guard rejects the shipped `JWT_SECRET`/admin password,
  short secrets, and a missing or identical `CUSTOMER_JWT_SECRET`; SMTP settings, `FRONTEND_URL`
  and the portal cookie names added.
- `app/main.py` â€” the wildcard CORS regex is limited to `NODE_ENV=development`; other environments
  use `CORS_ORIGINS` only.

Later fix (CORS preflight for credentialed frontend calls):

- `app/main.py` â€” `Access-Control-Allow-Origin: *` is never sent, because the browser rejects it on
  every request that sets `withCredentials` (all of `frontend/src/api/client.js`). A `*` in
  `CORS_ORIGINS` is no longer forwarded to `CORSMiddleware`; it becomes "mirror the requesting
  origin", the same mechanism the development regex uses, and logs a warning outside
  `NODE_ENV=development`.
- `app/core/config.py` â€” `cors_origin_list` drops a trailing slash from each origin, so
  `CORS_ORIGINS=http://localhost:5173/` matches the bare `Origin` header a browser sends instead of
  rejecting every preflight.
- `tests/test_middleware.py` â€” credentialed `POST /api/v1/auth/login` preflight asserts the origin is
  mirrored and never `*`; a wildcard config and a trailing-slash config are covered, and staging
  still rejects an origin outside the list. `tests/test_config.py` covers the parsing.
- `app/models/password_reset_token.py`, `app/repositories/password_reset_repository.py`,
  `app/services/password_reset_service.py`, `app/services/email_service.py`,
  `app/schemas/password_reset.py` (all new) â€” single-use staff and customer reset links, SHA-256
  at rest, scope binding, expiry, generic response, confirmation email.
- `app/routers/auth.py`, `app/routers/customer_auth.py` â€” `POST /forgot-password`,
  `GET /reset-password/validate`, `POST /reset-password` for both audiences.
- `alembic/versions/0003_password_reset.py` â€” `password_reset_tokens` table.
- `frontend/src/pages/ResetPassword/`, `frontend/src/pages/customer/Customer{Reset,Forgot}Password.jsx`,
  `frontend/src/components/PasswordResetForms.jsx` (new) â€” forgot/reset pages for staff and portal,
  linked from the login pages.
- `.env.example` â€” SMTP, `FRONTEND_URL` and reset-related comments.
- `tests/test_password_reset.py` (new, 15 tests) and `tests/test_middleware.py`
  (413/CORS; chunked bodies added in Phase 16).

## Phase 15 â€” session revocation and background email

Changed:

- `app/models/user.py`, `app/models/customer_portal_account.py` â€” `token_version` (int, default 0).
- `alembic/versions/0004_token_version.py` â€” adds the column to both tables; applied to the live
  DB on 2026-10-31 (`alembic current` â†’ `0004_token_version`).
- `app/core/security.py` â€” `ver` claim in staff and customer access/refresh tokens.
- `app/services/auth_service.py`, `app/services/customer_portal_auth_service.py` â€” login signs the
  current version; refresh rejects a mismatch with `401` "Session has expired; sign in again".
- `app/core/dependencies.py` â€” the bearer guards enforce the same check, so an access token minted
  before a reset stops working immediately.
- `app/services/password_reset_service.py` â€” reset bumps `token_version` in the same commit as the
  password and hash consume; portal deactivate/reactivate also bump it.
- `app/utils/tasks.py` (new) â€” `deliver_or_queue`; routers now pass `BackgroundTasks` so reset and
  activation emails are sent after the response instead of inside it.
- `tests/test_auth_sessions.py` (access/refresh revocation), `tests/test_customer_portal_auth.py`
  (customer refresh revocation), `tests/test_password_reset.py` (deferred email + version bump).

Verification (2026-10-31, observed):

```powershell
uv run ruff check app tests      # All checks passed
uv run alembic upgrade head      # 0003_password_reset -> 0004_token_version
uv run pytest -q                 # 378 passed, 150 subtests
```

## Phase 16 â€” post-audit fixes (2026-11-03)

Audit findings fixed:

- `app/services/user_service.py` â€” an administrative password change now bumps
  `token_version`, so the target's existing access/refresh tokens stop working; a
  deactivation/reactivation also bumps it (deactivation alone left old tokens usable
  again after reactivation); soft delete bumps it as defence in depth.
- `app/core/middleware.py` â€” the 1 MB body cap now also covers chunked requests with
  no `Content-Length` (or a lying one): the stream is buffered up to the limit and
  replayed to the app, returning the normal `PAYLOAD_TOO_LARGE` envelope on overflow.
- `app/services/email_service.py` â€” with SMTP unconfigured, the reset/activation link
  is echoed in the log only outside production; production logs name the failure
  without the live token.
- `app/core/config.py` â€” the production guard now rejects `FRONTEND_URL` values that
  are not a public `https` origin, since emailed links carry live reset tokens.
- `frontend/src/components/PasswordResetForms.jsx`, `frontend/src/pages/ResetPassword/`,
  `frontend/src/pages/customer/CustomerResetPassword.jsx` â€” a successful reset now
  clears the local session and refresh cookie, so the user reaches the sign-in form
  instead of bouncing through "session expired" (the API bumped `token_version`).
- New tests: `tests/test_config.py`, `tests/test_email_service.py`, chunked-body cases
  in `tests/test_middleware.py`, and staff password/status revocation cases in
  `tests/test_auth_and_users.py`.

Verification (2026-11-03, observed):

```powershell
uv run ruff check app tests      # All checks passed
uv run python -m compileall -q app tests
uv run pytest -q                 # 388 passed, 150 subtests
npm run lint                     # clean
npm run build                    # built (chunk-size warning only)
```

## Next step

1. Manual UAT and the clean-install/upgrade rehearsal described in
   `../docs/CUSTOMER_PORTAL_UAT_RELEASE.md` Â§4 (still N/R).
2. Optional: run the fake seeder against MySQL (`uv run python -m app.seeders.fake_indian_data`) to
   populate demo data; it writes rows and needs approval.
3. Optional: live side-by-side comparison of the Phase 9â€“11 endpoints and reports against Node.
4. Outstanding product decisions are listed in `HANDOFF.md` Â§6; deliberately not implemented:
   rate limiting and refresh-token rotation with server-side session records.

Migrations `0002`â€“`0004` are now applied to the development database; any further live DDL, a
production migration, or a live seed still needs separate approval.
