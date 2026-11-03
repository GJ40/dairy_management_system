"""Baseline existing MySQL schema.

Creates the ten core application tables in foreign-key dependency order:
  1. users
  2. buffaloes
  3. customers
  4. expense_categories
  5. milk_production
  6. milk_wastage
  7. sales
  8. invoices
  9. invoice_sales
  10. expenses

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. users
    # --------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'operator'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("email", "users", ["email"], unique=True)
    op.create_index("users_email", "users", ["email"], unique=True)
    op.create_index("username", "users", ["username"], unique=True)
    op.create_index("users_username", "users", ["username"], unique=True)

    # --------------------------------------------------------------------------
    # 2. buffaloes
    # --------------------------------------------------------------------------
    op.create_table(
        "buffaloes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tag_no", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("breed", sa.String(length=80), nullable=False),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("tag_no", "buffaloes", ["tag_no"], unique=True)
    op.create_index("buffaloes_tag_no", "buffaloes", ["tag_no"], unique=True)
    op.create_index("buffaloes_status", "buffaloes", ["status"])

    # --------------------------------------------------------------------------
    # 3. customers
    # --------------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("rate_per_litre", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("customers_is_active", "customers", ["is_active"])
    op.create_index("customers_name", "customers", ["name"])

    # --------------------------------------------------------------------------
    # 4. expense_categories
    # --------------------------------------------------------------------------
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("name", "expense_categories", ["name"], unique=True)
    op.create_index(
        "expense_categories_name", "expense_categories", ["name"], unique=True
    )

    # --------------------------------------------------------------------------
    # 5. milk_production
    # --------------------------------------------------------------------------
    op.create_table(
        "milk_production",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("buffalo_id", sa.Integer(), nullable=False),
        sa.Column("prod_date", sa.Date(), nullable=False),
        sa.Column("session", sa.String(length=20), nullable=False),
        sa.Column("litres", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["buffalo_id"],
            ["buffaloes.id"],
            name="milk_production_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name="milk_production_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "milk_production_buffalo_id_prod_date_session",
        "milk_production",
        ["buffalo_id", "prod_date", "session"],
        unique=True,
    )
    op.create_index(
        "milk_production_prod_date", "milk_production", ["prod_date"]
    )
    op.create_index(
        "milk_production_buffalo_id_prod_date",
        "milk_production",
        ["buffalo_id", "prod_date"],
    )
    op.create_index("recorded_by", "milk_production", ["recorded_by"])

    # --------------------------------------------------------------------------
    # 6. milk_wastage
    # --------------------------------------------------------------------------
    op.create_table(
        "milk_wastage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("waste_date", sa.Date(), nullable=False),
        sa.Column("litres", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name="milk_wastage_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("milk_wastage_waste_date", "milk_wastage", ["waste_date"])
    op.create_index("recorded_by", "milk_wastage", ["recorded_by"])

    # --------------------------------------------------------------------------
    # 7. sales
    # --------------------------------------------------------------------------
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("litres", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("rate", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "payment_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'unpaid'"),
        ),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="sales_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name="sales_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("sales_sale_date", "sales", ["sale_date"])
    op.create_index(
        "sales_customer_id_sale_date", "sales", ["customer_id", "sale_date"]
    )
    op.create_index("recorded_by", "sales", ["recorded_by"])

    # --------------------------------------------------------------------------
    # 8. invoices
    # --------------------------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_no", sa.String(length=60), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "total_amount", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "paid_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'unpaid'"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="invoices_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("invoice_no", "invoices", ["invoice_no"], unique=True)
    op.create_index(
        "invoices_invoice_no", "invoices", ["invoice_no"], unique=True
    )
    op.create_index("invoices_customer_id", "invoices", ["customer_id"])
    op.create_index(
        "invoices_period_start_period_end",
        "invoices",
        ["period_start", "period_end"],
    )

    # --------------------------------------------------------------------------
    # 9. invoice_sales
    # --------------------------------------------------------------------------
    op.create_table(
        "invoice_sales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="invoice_sales_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"],
            ["sales.id"],
            name="invoice_sales_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "invoice_sales_sale_id_invoice_id_unique",
        "invoice_sales",
        ["invoice_id", "sale_id"],
        unique=True,
    )
    op.create_index(
        "invoice_sales_sale_id", "invoice_sales", ["sale_id"], unique=True
    )
    op.create_index(
        "invoice_sales_invoice_id", "invoice_sales", ["invoice_id"]
    )

    # --------------------------------------------------------------------------
    # 10. expenses
    # --------------------------------------------------------------------------
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["expense_categories.id"],
            name="expenses_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name="expenses_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("expenses_expense_date", "expenses", ["expense_date"])
    op.create_index("expenses_category_id", "expenses", ["category_id"])
    op.create_index("recorded_by", "expenses", ["recorded_by"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("invoice_sales")
    op.drop_table("invoices")
    op.drop_table("sales")
    op.drop_table("milk_wastage")
    op.drop_table("milk_production")
    op.drop_table("expense_categories")
    op.drop_table("customers")
    op.drop_table("buffaloes")
    op.drop_table("users")
