# API Parity — Node.js/Express vs Python/FastAPI

**Status:** All 51 audited endpoints implemented — health/docs (Phase 1), auth/users/RBAC (Phase 3),
buffaloes + generic soft delete (Phase 4), production (Phase 5), stock/wastage (Phase 6),
customers/sales (Phase 7), invoices/payments/PDF (Phase 8), expenses (Phase 9), reports (Phase 10).
**Source:** `backend/src/routes`, `services`, `validators`, `middleware`, `utils/date.js`, `utils/errors.js`
**Target:** `backend_py/app/routers`, `app/schemas`, `app/services`
**Base URL used by frontend:** `http://localhost:8000/api/v1`
**Last updated:** 2026-10-29

> The documented contract is the Node behavior that the Python implementation reproduces. Implemented
> phases are verified with stdlib tests, fakes, and read-only live DB/API smoke checks; write paths
> have not been exercised against the live database.

---

## 1. Global contract (must match exactly)

| Item | Node behavior |
| --- | --- |
| Prefix | `/api/v1`; health also at `/health` |
| Content type | JSON except invoice PDF (`application/pdf`) and docs HTML |
| Auth header | `Authorization: Bearer <jwt>` |
| JWT payload | `{ id, email, username, role }`; HS256; no `sub`; expiry `JWT_EXPIRE_MINUTES` (default 480) |
| Roles | `admin`, `operator` |
| Success format | **Not uniform.** Preserve each route's envelope (see tables). |
| Error format | `{"error":{"code":"...","message":"...","details"?:...}}` |
| Error status | 400 most business/validation errors, 401 auth, 403 role, 404 missing, 409 duplicates, 500 internal |
| Validation failure | HTTP 400 `VALIDATION_ERROR`, message = first Zod issue as `"<field.path>: <message>"` (FastAPI's default 422 must be remapped) |
| Malformed JSON | HTTP 400 `INVALID_JSON` |
| Unknown route | 404 `NOT_FOUND` |
| Pagination defaults | `page=1`, `page_size=20`, max 100 |
| Pagination shape | `{items, page, page_size, total}`; invoices/expenses add `total_pages` |
| Dates | `YYYY-MM-DD` strings, business timezone `Asia/Kolkata` |
| Decimals | JSON **strings** with exactly 2 decimals, e.g. `"9.50"` (Sequelize DECIMAL behavior) |
| Timestamps | ISO-8601 strings from MySQL `DATETIME`, timezone `+05:30` |
| Date defaults | "today" computed in `Asia/Kolkata`, not server local time |
| Soft delete | `is_deleted = true`; normal reads exclude deleted rows (exceptions noted) |
| CORS | all origins with credentials unless `NODE_ENV=production` |
| Body limit | 1 MB |

### Error codes observed

`BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `DUPLICATE_ENTRY`, `INTERNAL_ERROR`,
`INVALID_JSON`, `VALIDATION_ERROR`, `FOREIGN_KEY_VIOLATION`,
`INVALID_PRODUCTION_DATE`, `OPERATOR_DATE_RESTRICTION`, `BUFFALO_NOT_ACTIVE`,
`INVALID_SALE_DATE`, `CUSTOMER_NOT_ACTIVE`, `INVALID_WASTAGE_DATE`,
`DUPLICATE_PRODUCTION_ENTRY`, `INVALID_DATE_RANGE`, `INVALID_QUANTITY`, `INVALID_RATE`,
`STOCK_INSUFFICIENT`, `UNSUPPORTED_RESOURCE`,
`DUPLICATE_CATEGORY`, `SALE_ALREADY_INVOICED`, `INVALID_SALE_FOR_INVOICE`.

---

## 2. Health and docs

| Method | Path | Auth | Parity requirement | Status |
| --- | --- | --- | --- | --- |
| GET | `/health` | public | `200` `{status:"ok",environment,uptime_seconds,timezone,timestamp,database:"connected"|"disconnected"}`; always 200 even if DB down | Implemented (Phase 1) |
| GET | `/api/v1/health` | public | same handler/body | Implemented (Phase 1) |
| GET | `/docs` | public | Swagger UI HTML | Implemented (Phase 1) |
| GET | `/api/v1/docs` | public | Swagger UI HTML | Implemented (Phase 1) |
| GET | `/api/v1/docs/openapi.json` | public | JSON spec; Node's file is stale/incomplete. Plan: serve generated spec, document deviation | Implemented (Phase 1; generated spec) |

Health notes: `uptime_seconds` is process uptime, rounded/floored per Node; `timestamp` ISO; the DB probe is a `SELECT 1` equivalent and must not raise.

---

## 3. Auth

| Method | Path | Auth | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/auth/login` | public | `{email: string(email), password: string(min 1)}`; email trimmed/lowercased | `200 {token, user}`; user excludes `password_hash`; `createdAt`/`updatedAt` | 400 `VALIDATION_ERROR`; 401 `UNAUTHORIZED` generic "Invalid email or password"; 401 `UNAUTHORIZED` "Account is deactivated. Please contact an administrator." for inactive; soft-deleted user treated as invalid | Implemented (Phase 3) |
| GET | `/auth/me` | any | — | `200 {user}`; `created_at`/`updated_at` (Node quirk) | 401 `UNAUTHORIZED` if missing/invalid token, deleted or inactive user | Implemented (Phase 3) |

Rules: bcrypt cost 10 (72-byte truncation); JWT HS256 payload `{id,email,username,role,iat,exp}`, expiry `JWT_EXPIRE_MINUTES`; reload user from DB every request; reject deleted/inactive; `requireRoles` returns 403 `FORBIDDEN` with `Access denied: Requires one of [admin] role`.

---

## 4. Users (admin only)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/users` | query `page`, `page_size`, `role`, `is_active`, `search` | `200 {items,page,page_size,total}`; camelCase timestamps | 400 validation; 403 | Implemented (Phase 3) |
| POST | `/users` | `{full_name, username, email, password(min 6), role (required admin\|operator)}` | `201 {user}`; camelCase timestamps | 409 `DUPLICATE_ENTRY` (email/username); 400 | Implemented (Phase 3) |
| GET | `/users/:id` | — | `200 {user}` | 404 | Implemented (Phase 3) |
| PUT | `/users/:id` | partial update incl. optional password | `200 {user}` | 404; 409 duplicate email/username; 400 | Implemented (Phase 3) |
| PATCH | `/users/:id/status` | `{is_active: boolean}` | `200 {user}` | 400 trying to deactivate self; 404 | Implemented (Phase 3) |
| DELETE | `/users/:id` | — | `200 {message,resource:"users",id,deleted_at}` | 400 deleting self; 400 target role is `admin`; 404 missing/deleted; 403 operator; 401 public | Implemented (Phase 13, Python only) |

Rules: email lowercase; username uniqueness; password hashed with bcrypt cost 10; `password_hash` never serialized. `POST /users` ignores `is_active` and always creates active users; `role` is required. User list/create/update/status return `createdAt`/`updatedAt`; `/auth/me` alone returns `created_at`/`updated_at`.

`DELETE /users/:id` is a Python-only addition (Node has no user delete route; its generic
`DELETE /:resource/:id` rejects `users`). It soft-deletes `operator` accounts by setting
`is_deleted=true` and `is_active=false`, keeps the row so `recorded_by` history stays intact, and
never cascades. Admin accounts are still managed by deactivation, and an admin cannot delete their
own account.

---

## 5. Buffaloes (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/buffaloes/count` | — | `200 {total,active,dry,sold,dead}` | — | Implemented (Phase 4) |
| GET | `/buffaloes` | `page`, `page_size`, `status`, `search` | `200 {items,page,page_size,total}`; sorted `created_at DESC` | 400 | Implemented (Phase 4) |
| POST | `/buffaloes` | `{tag_no, name, breed, dob?, purchase_date?, status?}` | `201 {buffalo}`; default `status=active` | 409 duplicate tag; 400 | Implemented (Phase 4) |
| GET | `/buffaloes/:id` | — | `200 {buffalo}` | 404 | Implemented (Phase 4) |
| PUT | `/buffaloes/:id` | partial update; `null` clears dates | `200 {buffalo}` | 404; 409 duplicate tag; 400 | Implemented (Phase 4) |

Rules: admin and operator; `tag_no` trimmed and stored uppercased; status one of `active,dry,sold,dead`; dates `DATEONLY` or null; deleted rows hidden; counts exclude deleted rows. Buffalo JSON includes `id,tag_no,name,breed,dob,purchase_date,status,is_deleted,createdAt,updatedAt`. Duplicate messages: create `Buffalo with tag number 'TAG' already exists`; update `Tag number 'TAG' is already assigned to another buffalo`.

---

## 6. Production (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/production/grid` | `date?` (default business today) | `200 {date,active_buffaloes_count,herd_totals{morning,evening,grand_total},grid[{buffalo_id,tag_no,name,breed,morning_litres,evening_litres,daily_total}]}` | 400 `INVALID_PRODUCTION_DATE` for future; 400 `VALIDATION_ERROR`; 403 | Implemented (Phase 5) |
| GET | `/production/summary` | `from`,`to` required | `200 {period{from,to},days_recorded,grand_total_litres,average_daily_litres,daily_summaries[{prod_date,morning_litres,evening_litres,total_litres}]}` | 400 missing/invalid; 400 `INVALID_DATE_RANGE` when `from>to` | Implemented (Phase 5) |
| GET | `/production/buffalo/:id` | `from?`,`to?` | `200 {buffalo{id,tag_no,name,breed,status},days_recorded,total_litres_produced,average_daily_yield,history[{prod_date,morning_litres,evening_litres,total_litres}]}` | 404 buffalo; 400 `INVALID_DATE_RANGE`; 400 `VALIDATION_ERROR` | Implemented (Phase 5) |
| GET | `/production` | `date?` (default business today) | `200 {date,herd_totals{morning,evening,grand_total},entries[...]}`; entries include `buffalo` and `recorder` | 400 `VALIDATION_ERROR`; 403 | Implemented (Phase 5) |
| POST | `/production` | single `{buffalo_id,prod_date,session,litres,overwrite?}` **or** bulk `{prod_date,entries[{buffalo_id,morning_litres?,evening_litres?,session?,litres?}],overwrite?}` | single: `201 {record}`; bulk: `201 {message:"Successfully saved N production entries",records[]}` | 400 `INVALID_PRODUCTION_DATE`; 403 `OPERATOR_DATE_RESTRICTION`; 400 `BUFFALO_NOT_ACTIVE`; 409 `DUPLICATE_PRODUCTION_ENTRY`; 400 `VALIDATION_ERROR` | Implemented (Phase 5) |

Rules and exact messages:

- Both admin and operator can access every production route.
- Future write date: 400 `INVALID_PRODUCTION_DATE`, `Production date cannot be in the future`.
- Future grid date: 400 `INVALID_PRODUCTION_DATE`, `Grid date cannot be in the future`.
- Operator non-today write: 403 `OPERATOR_DATE_RESTRICTION`, `Operators may only record or edit milk production for the current business day`.
- Missing buffalo: 404 `Buffalo with id {id} not found`; non-active: 400 `BUFFALO_NOT_ACTIVE`, `Buffalo '{tag}' is marked as '{status}' and cannot receive production entries. Only active buffaloes are eligible.`
- Single duplicate: 409 `DUPLICATE_PRODUCTION_ENTRY`, `A production entry already exists for buffalo id {id} on {date} ({session} session). Set overwrite: true to update.`
- Bulk duplicate: 409 `DUPLICATE_PRODUCTION_ENTRY`, `Production record already exists for {tag} on {date} ({session}). Use overwrite: true to confirm update.`
- Bulk writes are atomic: any validation/active-buffalo/duplicate failure rolls back all rows in that request. Bulk supports morning/evening pairs plus an explicit session/litres; an entry with no session values saves nothing but still validates the buffalo.
- `overwrite=true` updates the existing non-deleted row and sets `recorded_by` to the current user.
- Validation is Zod-compatible: `litres >= 0`, dates match `YYYY-MM-DD`, sessions are `morning|evening`, `overwrite` is a JSON boolean, buffalo IDs coerce to positive integers.
- Decimal responses are 2-decimal strings; grid daily total is null when both sessions are null; herd totals sum only present sessions.
- `GET /production` entries are ordered by `buffalo.tag_no ASC, session ASC`; history is ordered by `prod_date DESC, session ASC`; grid rows are active buffaloes only, sorted `tag_no ASC`.
- Summary/history aggregate per day in ascending order; history excludes production rows whose buffalo is soft-deleted via the buffalo lookup (404).
- Soft-deleted production rows are excluded from reads but still occupy the DB unique key `(buffalo_id,prod_date,session)`; a re-create collision maps to 409 `DUPLICATE_ENTRY`.

---

## 7. Stock (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/stock/history` | `from`,`to` required | `200 {period{from,to},history[{date,opening_stock,produced,sold,wasted,closing_stock}]}` | 400 missing/invalid; 400 `INVALID_DATE_RANGE` | Implemented (Phase 6) |
| GET | `/stock` | `date?` | `200 {date,opening_stock,produced,sold,wasted,closing_stock}` | 400 `VALIDATION_ERROR` | Implemented (Phase 6) |

Formulas (all soft-delete filtered, two-decimal strings):

```
opening = sum(production before date) - sum(sales before date) - sum(wastage before date)
closing = opening + produced - sold - wasted
```

Rules: `date` defaults to the business date. History requires both dates and rejects `from > to`
with 400 `INVALID_DATE_RANGE`, `'from' date cannot be after 'to' date`. Stock rows and history
values use `opening_stock`, `produced`, `sold`, `wasted`, `closing_stock`, all as 2-decimal
strings. The availability check used by wastage/sales is against the requested date **and all later
active dates**; a current shortfall returns `Only {available} L available`, while a future shortfall
returns the full margin message. Node has no lock; Phase 6 preserves that unlocked read-then-write
(see MIGRATION_PLAN §8.1).

---

## 8. Wastage (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/wastage` | `page`, `page_size`, `waste_date`, `from`, `to`, `reason` | `200 {items,page,page_size,total}`; items include `recorder` | 400 `VALIDATION_ERROR`; 400 `INVALID_DATE_RANGE` | Implemented (Phase 6) |
| POST | `/wastage` | `{waste_date, litres(>0), reason}` | `201 {wastage, stock_remaining}` | 400 `INVALID_WASTAGE_DATE`; 403 `OPERATOR_DATE_RESTRICTION`; 400 `INVALID_QUANTITY` / `STOCK_INSUFFICIENT` / validation | Implemented (Phase 6) |

Rules: reasons `spoiled,spilled,returned`; future date rejected; operator today only; insert and stock
check share one session and roll back together. `litres` is formatted to 2 decimals. The wastage
object includes `id,waste_date,litres,reason,recorded_by,is_deleted,createdAt,updatedAt`; list items
also include `recorder{id,full_name,username}`. Listing orders `waste_date DESC, created_at DESC`;
`waste_date` is exclusive and overrides `from`/`to`; range validation runs only when `waste_date` is
absent and both range dates are present. Pagination defaults 1/20, max 100.

---

## 9. Customers (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/customers/:id/balance` | — | `200 {customer_id,customer_name,rate_per_litre,is_active,total_sales_amount,total_paid_amount,outstanding_balance}` | 404 | Implemented (Phase 7) |
| GET | `/customers` | `page`, `page_size`, `search`, `is_active` | `200 {items,page,page_size,total}`; ordered `name ASC` | 400 | Implemented (Phase 7) |
| POST | `/customers` | `{name, phone?, address?, rate_per_litre(>0), is_active?}` | `201 {customer}`; `is_active` defaults true | 400 | Implemented (Phase 7) |
| GET | `/customers/:id` | — | `200 {customer}` | 404 | Implemented (Phase 7) |
| PUT | `/customers/:id` | partial update; `null` clears phone/address | `200 {customer}` | 404; 400 | Implemented (Phase 7) |

Rules: admin + operator. Customer JSON is
`id,name,phone,address,rate_per_litre,is_active,is_deleted,createdAt,updatedAt`; rates are 2-decimal
strings. Create trims name/phone/address, converts empty phone/address to null, and stores
`rate_per_litre` to 2 decimals. `search` trims and matches name/phone with `%term%`; `is_active`
filters booleans. Balance formula is
`sum(non-deleted sales.amount) - sum(non-deleted invoices.paid_amount)`, floored at 0. This counts
uninvoiced sales and can disagree with invoice statuses; the financial-semantics decision remains
open for Phase 8.

---

## 10. Sales (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/sales` | `page`, `page_size`, `customer_id`, `sale_date`, `from`, `to`, `payment_status` | `200 {items,page,page_size,total}`; items include customer (no address) + recorder | 400 `VALIDATION_ERROR`; 400 `INVALID_DATE_RANGE` | Implemented (Phase 7) |
| POST | `/sales` | `{customer_id, sale_date, litres(>0), rate?}` | `201` **flat sale fields + `stock_remaining`** (no `{sale}` wrapper) | 400 `INVALID_SALE_DATE`; 403 `OPERATOR_DATE_RESTRICTION`; 400 `CUSTOMER_NOT_ACTIVE`; 400 `STOCK_INSUFFICIENT`; 400 validation | Implemented (Phase 7) |
| GET | `/sales/:id` | — | `200 {sale}`; customer includes address | 404 | Implemented (Phase 7) |
| PUT | `/sales/:id` | partial `{sale_date?, litres?, rate?}` | `200 {sale}`; customer includes address | 404; 400 stock/validation | Implemented (Phase 7) |

Rules: admin + operator. Future date is rejected; operator may write only the current business day;
the customer must be active. `rate` defaults to the customer's `rate_per_litre`; amount is
`round(litres*rate, 2)`; payment status starts `unpaid`. Stock check and insert share one
transaction. Update recalculates amount and sets `recorded_by`; stock is re-checked only when litres
increase or the date changes, matching Node. List orders `sale_date DESC, created_at DESC`; exact
`sale_date` takes precedence over range filters; `from > to` is rejected only when no exact date is
present. Post/put response asymmetry is intentional. Sale JSON includes
`id,customer_id,sale_date,litres,rate,amount,payment_status,recorded_by,is_deleted,createdAt,updatedAt`;
list/detail add `customer` and `recorder`.

---

## 11. Invoices (admin + operator)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/invoices` | `page`, `page_size`, `customer_id`, `status`, `from`, `to` | `200 {items,page,page_size,total,total_pages}` | 400 | Implemented (Phase 8) |
| POST | `/invoices` | `{customer_id, period_start, period_end, sale_ids?}` | `201 {invoice}` | 400 invalid period; 400 `INVALID_SALE_FOR_INVOICE`; 409 `SALE_ALREADY_INVOICED`; 404 customer | Implemented (Phase 8) |
| GET | `/invoices/:id/pdf` | — | `200 application/pdf`, `Content-Disposition: inline` | 404 | Implemented (Phase 8) |
| GET | `/invoices/:id` | — | `200 {invoice}` incl. linked sales and `balance` | 404 | Implemented (Phase 8) |
| PATCH | `/invoices/:id/payment` | `{amount(>0)}` | `200 {invoice}` | 400 invalid/overpayment (decision); 404 | Implemented (Phase 8) |

Rules: invoice number `INV-YYYYMMDD-XXXX` (4 uppercase hex, 5 attempts, timestamp fallback); unique ignoring deleted; explicit `sale_ids` must belong to customer/period, be non-deleted, and not already linked (DB unique on `invoice_sales.sale_id`); period mode selects all uninvoiced non-deleted sales in range. Payment adds to `paid_amount`; status `unpaid/partial/paid`; when fully paid, update linked sales to `payment_status='paid'`. Node allows overpayment; ADR rejects it → decision required.

---

## 12. Expenses and categories (admin only)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/expenses/categories` | — | `200 {categories}` | 403 | Implemented (Phase 9) |
| POST | `/expenses/categories` | `{name}` | `201 {category}` | 409 `DUPLICATE_CATEGORY`; 400 | Implemented (Phase 9) |
| GET | `/expenses` | `page`, `page_size`, `category_id`, `from`, `to` | `200 {items,page,page_size,total,total_pages,total_expense_amount}` | 400 | Implemented (Phase 9) |
| POST | `/expenses` | `{category_id, expense_date, amount(>0), note?}` | `201 {expense}` | 400; 404 category | Implemented (Phase 9) |
| GET | `/expenses/:id` | — | `200 {expense}` | 404 | Implemented (Phase 9) |
| PUT | `/expenses/:id` | partial update | `200 {expense}` | 404; 400 | Implemented (Phase 9) |
| GET | `/expense-categories` | — | `200 {categories}` alias | 403 | Implemented (Phase 9) |

Rules: category names trimmed, lowercased, and unique among non-deleted rows; deleted categories and
expenses are excluded from reads. Expense JSON is
`id,category_id,expense_date,amount,note,recorded_by,is_deleted,createdAt,updatedAt` plus
`category{id,name}` and `recorder{id,full_name,username}`. List ordering is
`expense_date DESC, created_at DESC`; `from`/`to` apply only when both are present (no `from<=to`
validation in Node — preserved as a documented decision). `PUT` accepts partial fields and a `null`
`note` clears it.

---

## 13. Reports (mixed roles)

| Method | Path | Auth | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/reports/profit` | admin | `period?`, `from?`, `to?`, `month?` (`YYYY-MM`), `date?` | `200 {period,summary,category_breakdown,daily_breakdown}` | 400 invalid/ range | Implemented (Phase 10) |
| GET | `/reports/production` | admin+operator | `from?`,`to?` | `200` production summary | 400 | Implemented (Phase 10) |
| GET | `/reports/dashboard` | admin+operator | `date?` | `200` dashboard object; `financials` is `null` for operator | 400 | Implemented (Phase 10) |
| GET | `/reports/pdf` | admin (`type=profit`), admin+operator (`type=production\|dashboard`) | `type?` (`profit\|production\|dashboard`, default `profit`), `from?`, `to?`, `month?`, `date?` | `200 application/pdf`, `Content-Disposition: attachment; filename="dairy-<type>-report-<from>[_to_<to>].pdf"` | 400 invalid `type`/date/range; 403 operator requesting `profit`; 401 | Implemented (Phase 13, Python only) |

Profit: revenue = sum non-deleted sales in range; expenses = sum non-deleted expenses in range; profit = revenue − expenses; daily and category breakdowns; precedence `date` > `month` > `from/to` > current month; `period` is ignored by Node. Dashboard includes today's production, stock, sales, active buffalo count.

`GET /reports/pdf` is a Python-only addition (Node exports no report PDFs). It renders the same
payload the JSON routes return, so the PDF cannot drift from the API. Range resolution matches
`/reports/profit`; `type=dashboard` uses `date` when supplied and otherwise the end of the resolved
range's day. The document has a title/meta block, KPI strip, executive summary, A4 tables with
repeating headers, vector bar charts (revenue vs. expenses, expense categories, morning vs. evening
production), page numbering and a deliberate "No data for the selected period" block for empty
ranges. Rupee values are printed as `Rs. 1,234.00` because the base-14 PDF fonts do not carry the
U+20B9 glyph.

---

## 14. Soft delete (admin only)

| Method | Path | Request | Success | Errors | Status |
| --- | --- | --- | --- | --- | --- |
| DELETE | `/:resource/:id` | resource in allowlist | `200 {message,resource,id,deleted_at}` | 400 `UNSUPPORTED_RESOURCE`; 404 `NOT_FOUND`; 403 operator | Implemented (Phase 4) |

Allowlist: `buffaloes`, `customers`, `sales`, `invoices`, `expenses`, `production`, `wastage`. Admin only; sets `is_deleted=true` without cascading. `deleted_at` is UTC ISO. Node's not-found singularization strips only the final character (`buffaloe`, `productio`, `wastag`); preserved. `users` is intentionally not in this allowlist: user deletion has its own guarded `DELETE /users/:id` route (operator targets only), and `DELETE /users/:id` on the users router takes precedence over the generic `DELETE /:resource/:id`.

---

## 15. Parity test plan (per module)

For every endpoint: unauthenticated 401, wrong-role 403, happy path, not-found, validation 400, duplicate 409 where applicable, soft-deleted row hidden, pagination boundaries (1/20/100), date boundaries (today/future), decimal string formatting, and exact envelope keys.

Cross-module scenarios:

1. Production → stock → sale → wastage → stock changes.
2. Oversell attempt (single and two concurrent requests).
3. Duplicate production without/with `overwrite`.
4. Operator writes yesterday → 403; admin succeeds.
5. Invoice from period, duplicate sale rejection, payment partial → paid, PDF headers.
6. Profit: sales 5400, expenses 3900 → 1500.
7. Operator dashboard has `financials: null`.
8. Soft-deleted buffalo/sale hidden from lists and reports.
9. Reuse of a soft-deleted unique production/tag (known discrepancy).
10. Exact JSON types: DECIMAL as string, booleans, nulls, ISO timestamps.

Parity tests are implemented for Phases 1–11 with `pytest` (`210 passed`, 94 subtests) plus read-only
live DB/service smoke checks. Phase 13 adds tests for user deletion, report PDFs and invoice PDF
layout; they have **not been run yet** in the session that wrote them (the agent's shell could not
start), so the expected count is 233, not a verified result. Phases 9–11 are covered by unit/API
tests only so far; their live Node
comparison is still outstanding. The Node suite is not run because it targets and mutates the live MySQL
database.
