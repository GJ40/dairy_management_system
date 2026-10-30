# Migration Plan — Node.js/Express → Python/FastAPI

**Status:** Phase 0–12 complete. Live Alembic baseline stamped.
**Audit date:** 2026-10-28
**Source of truth for existing behavior:** `backend/` (Node.js + Express 5 + Sequelize + MySQL)
**Source of truth for scope:** `Dairy Management System – Project Requirements Document.md` (root)
**Target:** `backend_py/` (FastAPI foundation, SQLAlchemy models, Alembic baseline)

> The environment shell is `cmd.exe`, not PowerShell, so cmd-compatible commands were used.
> A read-only live schema inspection was performed in Phase 2, followed by an approved
> `alembic stamp head` that wrote only `alembic_version`. No application DDL, migration, seed, or
> data change was performed.

---

## 1. Relevant repository structure

```text
dairy_management_system/
├─ backend/                       Node.js reference implementation (do not modify)
│  ├─ .env                        present; variable NAMES inspected only
│  ├─ .env.example
│  ├─ package.json / package-lock.json
│  ├─ prisma/                     EMPTY (no schema.prisma)
│  ├─ src/
│  │  ├─ app.js, server.js
│  │  ├─ config/                  env.js, db.js
│  │  ├─ middleware/              auth, errorHandler, validate, requestLogger
│  │  ├─ migrations/runner.js     sequelize.sync({ force: false })
│  │  ├─ models/                  10 Sequelize models + associations
│  │  ├─ repositories/            10 repositories
│  │  ├─ routes/                  14 routers
│  │  ├─ services/                12 services
│  │  ├─ validators/              10 Zod validators
│  │  ├─ utils/                   date, errors, pdf
│  │  ├─ seeders/                 seed.js, fakeIndianData.js
│  │  └─ docs/openapi.json        STATIC and incomplete
│  └─ tests/                      15 Jest suites (hit the configured live MySQL DB)
├─ backend_py/                    target (FastAPI migration in progress)
│  ├─ .python-version             3.11
│  ├─ pyproject.toml / uv.lock
│  ├─ .venv/                      existing uv environment (do not recreate)
│  ├─ app/                        Phase 1 foundation + Phase 2 models
│  ├─ alembic.ini / alembic/      configured; empty baseline 0001_baseline
│  ├─ tests/                      23 stdlib tests (Phase 1 + models)
│  └─ README.md                   empty
├─ frontend/                      React/Vite client consuming this API
├─ docs/                          ADRs, RTM, implementation plan (partly aspirational)
└─ Dairy Management System – Project Requirements Document.md
```

Key facts:

- `backend/prisma/` is empty; the effective schema source is the Sequelize models plus `sequelize.sync()`.
- There are no `.sql` schema files in the repository.
- `backend_py` is a nested git repository with a working FastAPI foundation and models.

---

## 2. Node feature/module inventory

| Module | Files | Behavior summary |
| --- | --- | --- |
| App/bootstrap | `app.js`, `server.js` | Helmet (CSP off), permissive CORS with credentials, JSON/urlencoded 1 MB, cookie-parser, morgan, `/docs`, `/health`, `/api/v1/*`, 404 + central error envelope |
| Config | `config/env.js`, `config/db.js` | dotenv from `backend/.env`; MySQL via `DATABASE_URL` or discrete vars; pool 10; Sequelize timezone `+05:30`; TZ `Asia/Kolkata` |
| Auth | `middleware/auth.js`, `services/authService.js` | Bearer JWT; payload `{id,email,username,role,iat,exp}`; HS256; expiry `JWT_EXPIRE_MINUTES` (default 480); user reloaded per request; inactive/deleted rejected; `requireRoles(...)` |
| Users | `routes/users.js`, `services/userService.js` | Admin-only list/create/get/update/status; bcrypt cost 10; email lowercase; username unique; self-deactivation blocked |
| Buffaloes | `routes/buffaloes.js`, `services/buffaloService.js` | Admin+Operator; list/search/status/pagination; create with uppercase unique tag; get/update; status counts |
| Production | `routes/production.js`, `services/productionService.js` | Single or bulk POST; daily grid; daily list; range summary; buffalo history; duplicate `(buffalo,date,session)` conflict unless `overwrite`; operator current-day only; active buffalo only; no future dates |
| Stock | `routes/stock.js`, `services/stockService.js` | Derived opening/closing stock; history over a range; availability check against requested date and all later active dates |
| Wastage | `routes/wastage.js`, `services/wastageService.js` | Admin+Operator; list/filter/paginate; create in transaction after stock check; operator current-day only; reasons `spoiled|spilled|returned` |
| Customers | `routes/customers.js`, `services/customerService.js` | Admin+Operator; list/search/active/pagination; create/get/update; balance = sum(sales.amount) − sum(invoices.paid_amount), floor 0 |
| Sales | `routes/sales.js`, `services/saleService.js` | Admin+Operator; list/filter/paginate; create with stock check in transaction; amount = litres × rate; update with limited stock re-check; operator current-day only |
| Invoices | `routes/invoices.js`, `services/invoiceService.js` | Admin+Operator; create from explicit sale IDs or period; unique invoice no `INV-YYYYMMDD-XXXX`; prevents a sale being invoiced twice; list/detail; payment patch; PDF bytes |
| Expenses | `routes/expenses.js`, `services/expenseService.js` | Admin-only; categories list/create; expenses list/filter/paginate/total; create/get/update; category names lowercased and unique |
| Reports | `routes/reports.js`, `services/reportService.js` | Profit (Admin), production summary (Admin+Operator), dashboard (Admin+Operator, `financials:null` for Operator) |
| Delete | `routes/delete.js`, `services/deleteService.js` | Admin-only generic soft delete for `buffaloes, customers, sales, invoices, expenses, production, wastage` |
| Docs/health | `routes/docs.js`, `routes/health.js` | Static OpenAPI JSON; Swagger UI HTML from CDN; health at `/health` and `/api/v1/health` |
| Seeding | `seeders/seed.js`, `seeders/fakeIndianData.js` | Idempotent Admin + six default categories; Faker-style Indian demo data |

---

## 3. API endpoint inventory

Base prefix: `/api/v1`. All errors use `{"error":{"code":"...","message":"..."}}`.
Success envelopes are inconsistent by design and must be preserved (see `API_PARITY.md`).

| # | Method | Path | Auth/role | Notes |
| --- | --- | --- | --- | --- |
| 1 | GET | `/health` | public | DB ping; always 200 |
| 2 | GET | `/api/v1/health` | public | same handler |
| 3 | GET | `/docs` | public | Swagger UI HTML |
| 4 | GET | `/api/v1/docs` | public | Swagger UI HTML |
| 5 | GET | `/api/v1/docs/openapi.json` | public | static, incomplete spec |
| 6 | POST | `/auth/login` | public | `{email,password}` → `{token,user}` |
| 7 | GET | `/auth/me` | any | `{user}` |
| 8 | GET | `/users` | admin | `{items,page,page_size,total}` |
| 9 | POST | `/users` | admin | `{user}` |
| 10 | GET | `/users/:id` | admin | `{user}` |
| 11 | PUT | `/users/:id` | admin | `{user}` |
| 12 | PATCH | `/users/:id/status` | admin | `{user}` |
| 13 | GET | `/buffaloes/count` | admin+operator | `{total,active,dry,sold,dead}` |
| 14 | GET | `/buffaloes` | admin+operator | paginated `items` |
| 15 | POST | `/buffaloes` | admin+operator | `{buffalo}` |
| 16 | GET | `/buffaloes/:id` | admin+operator | `{buffalo}` |
| 17 | PUT | `/buffaloes/:id` | admin+operator | `{buffalo}` |
| 18 | GET | `/production/grid` | admin+operator | date defaults to business date |
| 19 | GET | `/production/summary` | admin+operator | requires `from`,`to` |
| 20 | GET | `/production/buffalo/:id` | admin+operator | optional `from`,`to` |
| 21 | GET | `/production` | admin+operator | optional `date` |
| 22 | POST | `/production` | admin+operator | single `{record}` or bulk `{message,records}` |
| 23 | GET | `/stock/history` | admin+operator | requires `from`,`to` |
| 24 | GET | `/stock` | admin+operator | optional `date` |
| 25 | GET | `/wastage` | admin+operator | paginated `items` |
| 26 | POST | `/wastage` | admin+operator | `{wastage,stock_remaining}` |
| 27 | GET | `/customers/:id/balance` | admin+operator | balance object |
| 28 | GET | `/customers` | admin+operator | paginated `items` |
| 29 | POST | `/customers` | admin+operator | `{customer}` |
| 30 | GET | `/customers/:id` | admin+operator | `{customer}` |
| 31 | PUT | `/customers/:id` | admin+operator | `{customer}` |
| 32 | GET | `/sales` | admin+operator | paginated `items` |
| 33 | POST | `/sales` | admin+operator | flat sale object + `stock_remaining` |
| 34 | GET | `/sales/:id` | admin+operator | `{sale}` |
| 35 | PUT | `/sales/:id` | admin+operator | `{sale}` |
| 36 | GET | `/invoices` | admin+operator | `{items,page,page_size,total,total_pages}` |
| 37 | POST | `/invoices` | admin+operator | `{invoice}` |
| 38 | GET | `/invoices/:id/pdf` | admin+operator | `application/pdf`, `Content-Disposition: inline` |
| 39 | GET | `/invoices/:id` | admin+operator | `{invoice}` with `balance` |
| 40 | PATCH | `/invoices/:id/payment` | admin+operator | `{invoice}` |
| 41 | GET | `/expenses/categories` | admin | `{categories}` |
| 42 | POST | `/expenses/categories` | admin | `{category}` |
| 43 | GET | `/expenses` | admin | `{items,page,page_size,total,total_pages,total_expense_amount}` |
| 44 | POST | `/expenses` | admin | `{expense}` |
| 45 | GET | `/expenses/:id` | admin | `{expense}` |
| 46 | PUT | `/expenses/:id` | admin | `{expense}` |
| 47 | GET | `/expense-categories` | admin | alias of 41 |
| 48 | GET | `/reports/profit` | admin | `{period,summary,category_breakdown,daily_breakdown}` |
| 49 | GET | `/reports/production` | admin+operator | same as production summary |
| 50 | GET | `/reports/dashboard` | admin+operator | financials only for admin |
| 51 | DELETE | `/:resource/:id` | admin | allowlist, soft delete, 200 `{message,resource,id,deleted_at}` |

---

## 4. Schema/table inventory (live-verified 2026-10-28)

Ten tables, created by `sequelize.sync({ force: false })`. All use `underscored: true` and timestamps `created_at`, `updated_at`. Live MySQL `8.0.33`, all `InnoDB` / `utf8mb4` / `utf8mb4_0900_ai_ci`.

| Table | Key columns / constraints |
| --- | --- |
| `users` | `id` PK AI; `full_name` VARCHAR(150) NN; `username` VARCHAR(80) NN UQ; `email` VARCHAR(150) NN UQ; `password_hash` VARCHAR(255) NN; `role` VARCHAR(30) NN default `operator`; `is_active` BOOL NN default 1; `is_deleted` BOOL NN default 0 |
| `buffaloes` | `id`; `tag_no` VARCHAR(50) NN UQ; `name` VARCHAR(100) NN; `breed` VARCHAR(80) NN; `dob` DATE null; `purchase_date` DATE null; `status` VARCHAR(30) NN default `active`; `is_deleted`; index on `status` |
| `milk_production` | `id`; `buffalo_id` FK→buffaloes NN; `prod_date` DATE NN; `session` VARCHAR(20) NN; `litres` DECIMAL(10,2) NN; `recorded_by` FK→users NN; `is_deleted`; UNIQUE(`buffalo_id`,`prod_date`,`session`); index `prod_date`; index `(buffalo_id,prod_date)` |
| `customers` | `id`; `name` VARCHAR(150) NN; `phone` VARCHAR(30) null; `address` TEXT null; `rate_per_litre` DECIMAL(10,2) NN; `is_active` BOOL NN default 1; `is_deleted`; indexes `is_active`, `name` |
| `sales` | `id`; `customer_id` FK NN; `sale_date` DATE NN; `litres` DECIMAL(10,2) NN; `rate` DECIMAL(10,2) NN; `amount` DECIMAL(12,2) NN; `payment_status` VARCHAR(20) NN default `unpaid`; `recorded_by` FK NN; `is_deleted`; indexes `sale_date`, `(customer_id,sale_date)` |
| `invoices` | `id`; `invoice_no` VARCHAR(60) NN UQ; `customer_id` FK NN; `period_start` DATE NN; `period_end` DATE NN; `total_amount` DECIMAL(12,2) NN; `paid_amount` DECIMAL(12,2) NN default 0; `status` VARCHAR(20) NN default `unpaid`; `is_deleted`; indexes `customer_id`, `(period_start,period_end)` |
| `invoice_sales` | `id`; `invoice_id` FK NN; `sale_id` FK NN UNIQUE; index `invoice_id` |
| `milk_wastage` | `id`; `waste_date` DATE NN; `litres` DECIMAL(10,2) NN; `reason` VARCHAR(30) NN; `recorded_by` FK NN; `is_deleted`; index `waste_date` |
| `expense_categories` | `id`; `name` VARCHAR(80) NN UQ; `is_deleted` |
| `expenses` | `id`; `category_id` FK NN; `expense_date` DATE NN; `amount` DECIMAL(12,2) NN; `note` TEXT null; `recorded_by` FK NN; `is_deleted`; indexes `expense_date`, `category_id` |

Enumerations are stored as VARCHAR + application validation, not MySQL ENUM.
`is_deleted` exists on `users` too, although the API never deletes users.

Live schema is verified: exact columns, nullability, defaults, duplicate unique indexes, ten
`ON DELETE CASCADE ON UPDATE CASCADE` FKs, engine, and collation. See `SCHEMA_MAPPING.md` for the
authoritative names and the read-only inspection record. The approved stamp created
`alembic_version` with `0001_baseline`.

---

## 5. Node dependencies and Python equivalents

| Node | Purpose | Python equivalent | Installed? |
| --- | --- | --- | --- |
| express | HTTP framework | fastapi 0.162.0 | YES |
| — | ASGI server | uvicorn 0.54.0 | YES |
| sequelize | ORM | sqlalchemy 2.1.6 | YES |
| mysql2 | MySQL driver | asyncmy 0.2.17 | YES (async only) |
| — | SQLAlchemy asyncio bridge | greenlet 3.5.6 | YES |
| — | IANA timezone database | tzdata 2026.6 | YES |
| — | sync MySQL driver | pymysql / mysqlclient | NO |
| zod | validation | pydantic 2.14.1 | YES |
| dotenv | env loading | pydantic-settings 2.16.2 / python-dotenv 1.2.4 | YES |
| jsonwebtoken | JWT | pyjwt 2.15.1 | YES |
| bcrypt | hashing | bcrypt 5.0.0 | YES |
| passlib | (not used) | — | NO (not needed) |
| pdfkit | PDF | reportlab 5.1.0 | YES |
| @faker-js/faker | demo data | faker 40.43.0 | YES |
| helmet/cors/morgan | headers/CORS/logging | Starlette middleware + logging | YES |
| jest/supertest | tests | pytest 9.2.0 + httpx 0.28.1 | YES |
| — | lint/format | ruff 0.17.3 | YES |
| alembic | migrations | alembic 1.20.1 | YES |
| sqlite3/pg/pg-hstore | archived alternatives | — | not needed |
| cookie-parser | cookies (unused by auth) | — | not needed |

Python interpreter: 3.11.15. `uv` 0.13.5. No package installation was performed.

---

## 6. Feature-by-feature mapping (Node → FastAPI destination)

| Feature | Node location | FastAPI destination | Phase |
| --- | --- | --- | --- |
| App, CORS, error envelope, 404, health | `src/app.js`, `middleware/errorHandler.js`, `routes/health.js` | `app/main.py`, `app/core/errors.py`, `app/routers/health.py` | 1 |
| Settings/env | `config/env.js` | `app/core/config.py` | 1 |
| DB engine/session | `config/db.js` | `app/db/session.py`, `app/db/base.py` | 1–2 |
| ORM models | `models/*.js` | `app/models/*.py` | 2 |
| Alembic | `migrations/runner.js` (sync only) | `alembic/` | 2 |
| JWT/password | `middleware/auth.js`, `services/authService.js` | `app/core/security.py`, `app/core/deps.py` | 3 |
| Users | `services/userService.js` | `app/services/user_service.py`, `app/routers/users.py` | 3 |
| Buffaloes | `services/buffaloService.js` | `app/services/buffalo_service.py`, `app/routers/buffaloes.py` | 4 |
| Production | `services/productionService.js` | `app/services/production_service.py`, `app/routers/production.py` | 5 |
| Stock/wastage | `services/stockService.js`, `services/wastageService.js` | `app/services/stock_service.py`, `app/services/wastage_service.py` | 6 |
| Customers/sales | `services/customerService.js`, `services/saleService.js` | `app/services/customer_service.py`, `app/services/sale_service.py` | 7 |
| Invoices/payments/PDF | `services/invoiceService.js`, `utils/pdf.js` | `app/services/invoice_service.py`, `app/utils/pdf.py` | 8 |
| Expenses | `services/expenseService.js` | `app/services/expense_service.py`, `app/routers/expenses.py` | 9 |
| Reports/dashboard | `services/reportService.js` | `app/services/report_service.py`, `app/routers/reports.py` | 10 |
| Soft delete | `services/deleteService.js` | `app/services/delete_service.py`, `app/routers/delete.py` | 4–10 |
| Seeders | `seeders/*.js` | `scripts/seed.py`, `scripts/seed_fake.py` | 11 |
| Tests | `backend/tests/*.js` | `backend_py/tests/*` | every phase |
| Docs/OpenAPI | `routes/docs.js`, `docs/openapi.json` | native FastAPI OpenAPI + `/docs` | 1/12 |

---

## 7. PRD coverage matrix

Legend: **N** = implemented in Node, **P** = partial, **M** = missing in Node.

| PRD requirement | Node source | Planned Python destination | Status | Tests needed |
| --- | --- | --- | --- | --- |
| FR-1 login/logout/me | `authService`, `routes/auth.js` | `core/security`, `routers/auth.py` | N | valid/invalid/inactive/token expiry |
| FR-1 Admin user CRUD/deactivate/roles | `userService`, `routes/users.js` | `routers/users.py` | N | duplicate email, operator 403 |
| FR-1 reset password | — | — | **M** | decision required |
| FR-2 buffalo CRUD/search/filter/count | `buffaloService` | `routers/buffaloes.py` | N | unique tag, counts, soft delete |
| FR-3 single/bulk production, totals | `productionService` | `routers/production.py` | N | uniqueness, totals, date rules |
| FR-3 buffalo-wise report by range | `productionService.getBuffaloProductionHistory` | same | P (single buffalo only) | range totals |
| FR-4 derived stock | `stockService` | `stock_service.py` | N | worked example, oversell |
| FR-4 wastage | `wastageService` | `wastage_service.py` | N | reasons, stock guard |
| FR-5 customer CRUD/balance | `customerService` | `customer_service.py` | N | rate, balance |
| FR-5 customer sales history endpoint | — (filter sales by customer only) | — | **P/M** | decision required |
| FR-6 sales create/list/get/update | `saleService` | `sale_service.py` | N | amount, stock, inactive customer |
| FR-6 invoice per sale / monthly | `invoiceService` | `invoice_service.py` | P (period or explicit IDs; no per-sale shortcut) | unique no, duplicate prevention |
| FR-6 PDF | `utils/pdf.js` | `utils/pdf.py` | N | headers, totals |
| FR-6 paid/partial/unpaid | invoice status; sale status only unpaid/paid | same | P (inconsistent source of truth) | decision required |
| FR-7 expenses/categories admin-only | `expenseService` | `expense_service.py` | N | operator 403, totals |
| FR-8 dashboard | `reportService.getDashboardOverview` | `report_service.py` | N | financial masking |
| FR-8 profit report | `reportService.getProfitReport` | same | N | 5400−3900=1500 |
| FR-8 CSV/PDF report export | — | — | **M** | decision required |
| Soft delete + exclusion | `deleteService`, repository filters | `delete_service.py` | P (see bugs) | hidden and excluded |
| Error envelope/status codes | `errorHandler.js` | exception handlers | N | 400/401/403/404/409 |
| `/api/v1` prefix | `routes/index.js` | router prefix | N | smoke |
| ISO dates, Asia/Kolkata, Decimal | `utils/date.js`, models | `utils/date.py`, Pydantic serializers | N | exact two-decimal strings |

---

## 8. Bugs, missing features, discrepancies, ambiguities

### High risk (behavior/data decisions needed)

1. **Concurrency is not actually serialized in Node.** The PRD/ADR require a lock, but `assertAvailableStock` is a read-then-write inside a default MySQL transaction with no `FOR UPDATE`/`GET_LOCK`. Concurrent sales can oversell. Decision: preserve Node behavior or implement the PRD's safe sugar? Recommendation: MySQL `GET_LOCK('dairy_stock_lock', ...)` around the stock check + write (no schema change), with an explicit deviation note.
2. **Soft-deleted production blocks re-entry.** UNIQUE(`buffalo_id`,`prod_date`,`session`) does not include `is_deleted`; the service ignores deleted rows, then the insert fails with `DUPLICATE_ENTRY`. Same class of issue for soft-deleted buffalo tags and customer names (buffalo tag has a DB unique). Decision needed on restore/update-vs-conflict semantics.
3. **Payment source of truth is inconsistent.** Invoice payments update `invoices.paid_amount/status`; sales only flip to `paid` on full payment and never move to `partial`. Customer balance uses `sum(sales.amount) − sum(invoices.paid_amount)` (floored at 0), which mixes invoiced and uninvoiced sales. ADR-004 describes a different formula. Node also allows overpayment; ADR says reject it. Need approval before changing financial semantics.
4. **Soft-deleted invoices keep their `invoice_sales` links**, so those sales can never be re-invoiced (409 `SALE_ALREADY_INVOICED`). A soft-deleted sale still appears inside invoice detail (the invoice→sales include does not filter `is_deleted`), while invoice totals stay unchanged.
5. **Operator permissions conflict.** PRD §4 says Operator may "create, view, print" sales/invoices; Node also allows `PUT /sales/:id` and invoice payment updates; README says "edit". Need a decision.

### Missing PRD functionality in Node

6. No password reset endpoint (PRD FR-1, RTM lists `POST /users/{id}/reset-password`).
7. No customer sales-history endpoint (RTM lists `GET /customers/{id}/sales`; only a generic sales filter exists).
8. No CSV report export and no PDF report export (PRD FR-8).
9. No monthly "one invoice per customer" convenience endpoint beyond selecting a period.
10. Static `docs/openapi.json` lists only a subset of real routes and lacks request/response schemas; it is not a reliable contract.

### Contract/semantic discrepancies

11. **JWT claims:** Node uses `{id,email,username,role}` with no `sub`; ADR-007 planned `sub`. Preserve Node for frontend compatibility.
12. **Database:** PRD/root README say PostgreSQL; actual active backend and your instruction say MySQL. Follow MySQL.
13. **Inactive login message:** Node returns a specific "Account is deactivated..." message (tests require it), while wrong credentials use the generic message. Preserve.
14. **Invoice list period filter** is containment (`period_start >= from AND period_end <= to`), not overlap.
15. **Soft-deleted users:** users are never soft-deleted via API, but the unique email/username constraints would still block reuse if one existed.
16. **User role changes** have no last-admin or self-demotion guard (only self-deactivation is blocked).
17. **Expense/date filters:** `expenseService.listExpenses` does not validate `from <= to`; other modules do.
18. **Profit report** ignores the `period` enum value; precedence is `date` > `month` > `from/to` > current month.
19. **Production history** has no pagination and `average_daily_yield` divides by distinct recorded days.
20. **Future dates:** production create and grid reject them; `GET /production?date=` and summary do not.
21. **Sale update** re-checks stock only when litres increase or the date changes; decreasing litres is unchecked (safe for stock, but no explicit rule).
22. **Timestamps/decimals:** Sequelize returns `DECIMAL` as strings (e.g. `"9.50"`); FastAPI must serialize `Decimal` with exactly two places to keep the frontend contract.

### Repository/tooling issues

23. `backend_py` is empty scaffolding: no settings, models, routers, Alembic config, or tests. `app/main.py` is 0 bytes.
24. `backend_py` has no `.env` or `.env.example`. Variables must be defined in Phase 1.
25. `pytest` and `ruff` are installed as of Phase 3; tests and lint run with `uv run`.
26. Only `asyncmy` is installed; SQLAlchemy must run async or a sync driver needs approval.
27. The Node tests connect to the configured live MySQL and call `destroy()`/create rows. They must not be run against the real DB.
28. Node README/RTM mention routes that do not exist (`/production/bulk`, `/users/:id/reset-password`, `/customers/:id/sales`, `/reports/export/*`).
29. Root README still describes PostgreSQL; stale.
30. `backend_py` is its own git repo nested in a non-git root.

---

## 9. Migration order, dependencies, risks

Recommended order (one phase per approval):

1. **Foundation** — settings, engine/session, logging, CORS, error envelope, health, docs.
2. **Models + Alembic baseline** — [x] 10 models match the live snapshot; empty baseline created and stamped.
3. **Auth/users/RBAC** — [x] login, JWT, `/auth/me`, admin user CRUD/status, RBAC; 72 tests pass.
4. **Buffaloes** — [x] CRUD, counts, filters, and generic soft delete; 103 tests pass.
5. **Production** — [x] grid/list/summary/history and atomic single/bulk writes; 125 tests passed.
6. **Stock/wastage** — [x] derived stock, history, availability guards, and transactional wastage;
   139 tests pass. Concurrency still follows Node's unlocked read-then-write.
7. **Customers/sales** — [x] customer CRUD/balance and transactional sales create/update with stock
   guards; 154 tests pass.
8. **Invoices/payments/PDF** — depends on sales/customers.
9. **Expenses** — independent after auth.
10. **Dashboard/reports** — depends on all aggregates; add exports if approved.
11. **Faker seeds** — depends on models and auth.
12. **Parity audit/handoff** — route-by-route verification, OpenAPI, docs.

Main risks: concurrency semantics, unique constraints vs soft delete, invoice/payment source of truth, decimal/timestamp serialization, live-schema drift, missing test tooling, and scope creep from PRD features absent in Node.

---

## 10. Safe Alembic baseline strategy for an existing MySQL schema

Do **not** generate and apply an initial "create all tables" migration against the live DB.

Baseline status:

1. [x] Read-only inspected `information_schema` / `SHOW CREATE TABLE` for the 10 tables, indexes, FKs, and column types.
2. [x] Compared the snapshot with SQLAlchemy metadata; `SCHEMA_MAPPING.md` records the result (exact match).
3. [x] Created `alembic.ini` + async `alembic/env.py` with `target_metadata = Base.metadata`; URL comes from `settings`.
4. [x] Created empty baseline revision `0001_baseline` (no DDL).
5. [x] Validated offline: `alembic upgrade head --sql` emits only `CREATE TABLE alembic_version` + the baseline INSERT; no application `CREATE TABLE`/`ALTER TABLE`.
6. [x] After explicit approval: `alembic stamp head` executed (metadata-only). Live `alembic_version` contains `0001_baseline`.
7. Every later schema change becomes a new revision; never `downgrade` or reset production data.
8. Optional validation against a disposable database (creating a DB requires separate approval; no SQLite substitution).
9. Keep `sequelize.sync()` out of the Python project entirely.

Driver decision: async SQLAlchemy with `asyncmy` (resolved).

---

## 11. Faker seed plan and safety/idempotency

Mirror `seed.js` and `fakeIndianData.js`, but safer:

- Base seed: six categories (`feed, labour, medicine, electricity, transport, other`), lowercased, find-or-create; first Admin from `ADMIN_*` environment variables only. Never hardcode credentials; never log the password.
- Demo seed: deterministic RNG (`Faker.seed(...)`), fixed operator emails, fixed buffalo tags `TAG-0101…`, deterministic customer names.
- FK-safe order: users → buffaloes/customers/categories → production → wastage → sales → invoices → invoice_sales → expenses.
- Idempotency strategy:
  - categories by unique name; admin/operators by unique email;
  - buffaloes by unique tag;
  - production/wastage/invoice_sales by their unique keys;
  - sales have no natural unique key: skip a customer/date pair if any seeded sale already exists (or use a deterministic marker note/rate); never rely on random litres for identity;
  - invoices by deterministic invoice number (≤60 chars);
  - expenses: check category+date+amount+note before insert, or use a deterministic note.
- `--dry-run` prints planned inserts and refuses to write.
- Never truncate, delete, or overwrite existing users/records. Never touch a non-development target without explicit approval.
- Tests only against a disposable/approved database.

---

## 12. Open questions for approval

1. Concurrency: preserve Node's unlocked read-then-write, or implement MySQL `GET_LOCK` serialization per the PRD?
2. Soft-deleted unique rows: on re-entry, restore/overwrite the deleted row, or return a clear conflict?
3. Payments: preserve Node (overpayment allowed, sales only `unpaid|paid`, balance formula as implemented), or align to ADR-004?
4. Operator sales/invoice edits: keep Node (edit + payment allowed) or restrict to create/view/print per PRD §4?
5. Are password reset, customer sales history, and CSV/PDF report exports in scope for this migration?
6. [x] JWT confirmed as `{id,email,username,role}` plus `iat`/`exp` (not `sub`).
7. [x] Live DB: read-only schema inspection completed in Phase 2.
8. [x] `pytest` and `ruff` installed; `pytest-asyncio`/`pytest-cov` not needed.
9. [x] Driver: async SQLAlchemy with installed `asyncmy`.
10. [x] `alembic stamp head` executed on the live DB; only `alembic_version` was written.
