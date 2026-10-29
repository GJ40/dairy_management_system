# Schema Mapping — Sequelize/MySQL → SQLAlchemy/Alembic

**Status:** Live MySQL schema inspected; models match; Alembic baseline stamped.
**Source of truth:** live MySQL 8.0.33 metadata + `backend/src/models/*.js`
**Target:** `backend_py/app/models/*.py` + `backend_py/alembic/`
**Last updated:** 2026-10-28

> Live inspection was read-only (`SHOW CREATE TABLE` + `information_schema`). The ten application
> tables already exist and are owned by the Node/Sequelize app. `Base.metadata` was compared
> programmatically against the live snapshot: all 10 tables, columns, types, nullability, defaults,
> indexes, foreign keys, engine, and collation match. `alembic stamp head` was then executed with
> explicit approval; it created only `alembic_version` and recorded `0001_baseline`.

---

## 1. Global mapping rules

| Sequelize / MySQL | SQLAlchemy | Notes |
| --- | --- | --- |
| `INTEGER` PK + `autoIncrement` | `Integer, primary_key=True, autoincrement=True` | MySQL `INT AUTO_INCREMENT` |
| `STRING(n)` | `String(n)` | `VARCHAR(n)` |
| `TEXT` | `Text` | `TEXT` |
| `DATEONLY` | `Date` | Python `datetime.date`; serialize `YYYY-MM-DD` |
| `DECIMAL(p,s)` | `Numeric(p,s)` | preserve `Decimal`; JSON as 2-decimal string |
| `BOOLEAN` | `Boolean` | MySQL `TINYINT(1)` |
| `created_at` / `updated_at` | `DateTime` + Python `default`/`onupdate` | MySQL `DATETIME` has **no DB default**; app writes `+05:30` wall-clock values |
| `references: {model, key}` | `ForeignKey("table.id")` | Live FKs are `ON DELETE CASCADE ON UPDATE CASCADE` |
| `underscored: true` | explicit snake_case column names | Do not rely on automatic naming |
| `timestamps: true` | `created_at`, `updated_at` | `updated_at` auto-updates in the ORM |
| `is_deleted` | `Boolean, nullable=False, default=False` | soft delete; no global filter |
| `unique: true` + model `indexes` | unique constraint/index | **Confirmed:** several columns have two unique indexes in MySQL |

### Critical Alembic naming caveat

Do **not** apply a new `naming_convention` blindly to existing tables. The real index and FK names
were read from `information_schema` and are declared explicitly in `__table_args__` /
`Index(...)` / `ForeignKey(name=...)`. No global naming convention is configured. Future
migrations must use explicit names or a convention that does not rewrite existing objects.

### Timestamps and timezone

- Sequelize connection timezone: `+05:30`; business TZ: `Asia/Kolkata`.
- MySQL `DATETIME` is timezone-naive; Python must not attach/convert timezone unexpectedly.
- Node returns timestamps as ISO strings; confirm exact serialization (including `Z`/offset) against the live API before locking it in tests.

### Decimal serialization

Sequelize/MySQL returns `DECIMAL` values as strings, usually with the column scale (`"9.50"`,
`"0.00"`). Pydantic's default `Decimal` JSON output may drop trailing zeros. Use an explicit
serializer that formats `quantize(Decimal("0.01"))` as a string for every monetary/litre field.

### Collation/charset

Verified live: all tables are `InnoDB`, `utf8mb4`, collation `utf8mb4_0900_ai_ci`. The models
declare `mysql_engine`, `mysql_charset`, and `mysql_collate` explicitly to match.

---

## 2. Table-by-table mapping

### 2.1 `users` → `User`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | auto increment | PK |
| `full_name` | `VARCHAR(150)` | no | — | — |
| `username` | `VARCHAR(80)` | no | — | UNIQUE |
| `email` | `VARCHAR(150)` | no | — | UNIQUE; app lowercases/trims |
| `password_hash` | `VARCHAR(255)` | no | — | never serialized |
| `role` | `VARCHAR(30)` | no | `'operator'` | app enum `admin,operator` |
| `is_active` | `TINYINT(1)` | no | `1` | — |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at` | `DATETIME` | no | — | — |
| `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `email`, UNIQUE `users_email`, UNIQUE `username`, UNIQUE `users_username`.
The duplicate unique indexes exist because Sequelize declared both `unique: true` and an explicit
index. Keep all four names.

### 2.2 `buffaloes` → `Buffalo`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `tag_no` | `VARCHAR(50)` | no | — | UNIQUE; app stores uppercase |
| `name` | `VARCHAR(100)` | no | — | — |
| `breed` | `VARCHAR(80)` | no | — | — |
| `dob` | `DATE` | yes | `NULL` | — |
| `purchase_date` | `DATE` | yes | `NULL` | — |
| `status` | `VARCHAR(30)` | no | `'active'` | app enum `active,sold,dry,dead` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `tag_no`, UNIQUE `buffaloes_tag_no`, INDEX `buffaloes_status` (`status`).

### 2.3 `milk_production` → `MilkProduction`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `buffalo_id` | `INT` | no | — | FK → `buffaloes.id` |
| `prod_date` | `DATE` | no | — | — |
| `session` | `VARCHAR(20)` | no | — | app enum `morning,evening` |
| `litres` | `DECIMAL(10,2)` | no | — | app min 0 |
| `recorded_by` | `INT` | no | — | FK → `users.id` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `milk_production_buffalo_id_prod_date_session`
(`buffalo_id`,`prod_date`,`session`), INDEX `milk_production_prod_date`, INDEX
`milk_production_buffalo_id_prod_date`, INDEX `recorded_by`. **The unique key ignores
`is_deleted`** → soft-deleted rows block re-entry.

### 2.4 `milk_wastage` → `MilkWastage`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `waste_date` | `DATE` | no | — | — |
| `litres` | `DECIMAL(10,2)` | no | — | app min 0.01 |
| `reason` | `VARCHAR(30)` | no | — | app enum `spoiled,spilled,returned` |
| `recorded_by` | `INT` | no | — | FK → `users.id` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: INDEX `milk_wastage_waste_date`, INDEX `recorded_by`.

### 2.5 `customers` → `Customer`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `name` | `VARCHAR(150)` | no | — | — |
| `phone` | `VARCHAR(30)` | yes | `NULL` | — |
| `address` | `TEXT` | yes | `NULL` | — |
| `rate_per_litre` | `DECIMAL(10,2)` | no | — | app min 0.01 |
| `is_active` | `TINYINT(1)` | no | `1` | — |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: INDEX `customers_is_active`, INDEX `customers_name`.

### 2.6 `sales` → `Sale`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `customer_id` | `INT` | no | — | FK → `customers.id` |
| `sale_date` | `DATE` | no | — | — |
| `litres` | `DECIMAL(10,2)` | no | — | app min 0.01 |
| `rate` | `DECIMAL(10,2)` | no | — | app min 0.01 |
| `amount` | `DECIMAL(12,2)` | no | — | app min 0; computed |
| `payment_status` | `VARCHAR(20)` | no | `'unpaid'` | app enum `unpaid,paid` |
| `recorded_by` | `INT` | no | — | FK → `users.id` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: INDEX `sales_sale_date`, INDEX `sales_customer_id_sale_date`
(`customer_id`,`sale_date`), INDEX `recorded_by`.

### 2.7 `invoices` → `Invoice`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `invoice_no` | `VARCHAR(60)` | no | — | UNIQUE |
| `customer_id` | `INT` | no | — | FK → `customers.id` |
| `period_start` | `DATE` | no | — | — |
| `period_end` | `DATE` | no | — | — |
| `total_amount` | `DECIMAL(12,2)` | no | — | app min 0 |
| `paid_amount` | `DECIMAL(12,2)` | no | `0.00` | app min 0 |
| `status` | `VARCHAR(20)` | no | `'unpaid'` | app enum `unpaid,partial,paid` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `invoice_no`, UNIQUE `invoices_invoice_no`, INDEX
`invoices_customer_id`, INDEX `invoices_period_start_period_end`
(`period_start`,`period_end`).

### 2.8 `invoice_sales` → `InvoiceSale`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `invoice_id` | `INT` | no | — | FK → `invoices.id` |
| `sale_id` | `INT` | no | — | UNIQUE; FK → `sales.id` |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `invoice_sales_sale_id` (`sale_id`), INDEX
`invoice_sales_invoice_id`, UNIQUE `invoice_sales_sale_id_invoice_id_unique`
(`invoice_id`,`sale_id`). **No `is_deleted` column.** The composite unique is redundant with the
single-column `sale_id` unique but must be preserved.

### 2.9 `expense_categories` → `ExpenseCategory`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `name` | `VARCHAR(80)` | no | — | UNIQUE; app lowercases/trims |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: UNIQUE `name`, UNIQUE `expense_categories_name`.

### 2.10 `expenses` → `Expense`

| Column | MySQL type | Null | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | `INT` | no | AI | PK |
| `category_id` | `INT` | no | — | FK → `expense_categories.id` |
| `expense_date` | `DATE` | no | — | — |
| `amount` | `DECIMAL(12,2)` | no | — | app min 0.01 |
| `note` | `TEXT` | yes | `NULL` | — |
| `recorded_by` | `INT` | no | — | FK → `users.id` |
| `is_deleted` | `TINYINT(1)` | no | `0` | soft delete |
| `created_at`, `updated_at` | `DATETIME` | no | — | — |

Live indexes: INDEX `expenses_expense_date`, INDEX `expenses_category_id`, INDEX `recorded_by`.

---

## 3. Foreign keys (verified live)

All ten foreign keys are `ON DELETE CASCADE ON UPDATE CASCADE`.

| Constraint | Child column | Parent |
| --- | --- | --- |
| `milk_production_ibfk_1` | `milk_production.buffalo_id` | `buffaloes.id` |
| `milk_production_ibfk_2` | `milk_production.recorded_by` | `users.id` |
| `milk_wastage_ibfk_1` | `milk_wastage.recorded_by` | `users.id` |
| `sales_ibfk_1` | `sales.customer_id` | `customers.id` |
| `sales_ibfk_2` | `sales.recorded_by` | `users.id` |
| `invoices_ibfk_1` | `invoices.customer_id` | `customers.id` |
| `invoice_sales_ibfk_1` | `invoice_sales.invoice_id` | `invoices.id` |
| `invoice_sales_ibfk_2` | `invoice_sales.sale_id` | `sales.id` |
| `expenses_ibfk_1` | `expenses.category_id` | `expense_categories.id` |
| `expenses_ibfk_2` | `expenses.recorded_by` | `users.id` |

Application deletes are soft deletes, so the DB cascades only matter for hard deletes/cleanup.

---

## 4. Model conventions for the Python project

- SQLAlchemy 2.x declarative (`DeclarativeBase`, `Mapped[...]`, `mapped_column`).
- Explicit `__tablename__` and explicit column names; no automatic pluralization.
- `__table_args__` carries the real index/constraint names from live inspection.
- Relationships: `Buffalo.productions`, `User.productions`, `User.sales`, `Customer.sales`,
  `Customer.invoices`, `Invoice.sales` (secondary `invoice_sales`), `ExpenseCategory.expenses`.
  `invoice_sales` is a link table with its own PK; use an association object, not a plain
  `secondary`, if timestamps/IDs must be preserved.
- No global `is_deleted` filter in the ORM; filter in repositories to mirror Node's explicit
  `where: { is_deleted: false }`.
- Do not enable `lazy="joined"` globally; match Node's explicit includes.

---

## 5. Alembic baseline procedure

1. [x] **Read-only live inspection** completed:
   - `information_schema.COLUMNS` for the 10 tables (type, nullability, default, extra, charset).
   - `information_schema.STATISTICS` for index names, uniqueness, column order.
   - `information_schema.KEY_COLUMN_USAGE` / `REFERENTIAL_CONSTRAINTS` for FK names and rules.
   - `SHOW CREATE TABLE` for each table (authoritative DDL snapshot).
   - `alembic_version` absent (confirmed).
2. [x] `alembic.ini` + async `alembic/env.py` written; URL comes from `settings`, never from the ini.
3. [x] Models defined and compared programmatically to the snapshot: no mismatches.
4. [x] Empty baseline revision `0001_baseline` created with no DDL.
5. [x] `alembic upgrade head --sql` offline review: emits only `CREATE TABLE alembic_version` and
   the baseline INSERT; no application `CREATE TABLE`/`ALTER TABLE`.
6. [x] **With explicit approval:** `alembic stamp head` executed. Live `alembic_version` contains
   `0001_baseline`; 11 tables total (original 10 + `alembic_version`); no application DDL.
7. Future changes: new revisions with explicit names; never downgrade/reset production.
8. Optional: validate on a disposable database (separate approval; no SQLite substitution).

Never run `alembic revision --autogenerate` against the live DB and apply the resulting initial
migration. It would attempt to recreate existing tables.

---

## 6. Verification checklist (Phase 2)

- [x] All 10 tables and exact column types match.
- [x] `DECIMAL` precision/scale match (10,2 vs 12,2).
- [x] Nullability and defaults (`role`, `status`, booleans, `paid_amount`) match.
- [x] Duplicate unique indexes identified and reproduced exactly (not consolidated).
- [x] Real index names captured (Sequelize-generated vs custom).
- [x] FK names and `ON DELETE CASCADE ON UPDATE CASCADE` captured.
- [x] Charset/collation captured (`InnoDB`, `utf8mb4`, `utf8mb4_0900_ai_ci`).
- [x] `created_at`/`updated_at` defaults/on-update behavior captured (Python-side only).
- [x] `alembic_version` absent before stamping.
- [x] No application DDL executed; no application rows created/updated/deleted.
- [x] Alembic baseline stamped (`0001_baseline`), verified read-only after the stamp.
