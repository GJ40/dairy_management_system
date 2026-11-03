"""Add customer portal tables.

Revision ID: 0002_customer_portal
Revises: 0001_baseline
Create Date: 2026-10-30

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002_customer_portal"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('customers'):
        import importlib.util
        from pathlib import Path
        bf = Path(__file__).parent / '0001_baseline_existing_schema.py'
        if bf.exists():
            spec = importlib.util.spec_from_file_location('baseline_0001', bf)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.upgrade()
    op.create_table(
        "customer_portal_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("activation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("activation_expires_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
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
            name="fk_customer_portal_accounts_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_portal_accounts_customer_id",
        "customer_portal_accounts",
        ["customer_id"],
        unique=True,
    )
    op.create_index(
        "customer_portal_accounts_email",
        "customer_portal_accounts",
        ["email"],
        unique=True,
    )
    op.create_index(
        "customer_portal_accounts_is_active",
        "customer_portal_accounts",
        ["is_active"],
    )

    op.create_table(
        "customer_portal_account_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["customer_portal_accounts.id"],
            name="fk_customer_portal_account_events_account_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_customer_portal_account_events_actor_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_portal_account_events_account_id_created_at",
        "customer_portal_account_events",
        ["account_id", "created_at"],
    )

    op.create_table(
        "customer_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=30), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("requested_date", sa.Date(), nullable=False),
        sa.Column("quantity_litres", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("rate_snapshot", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("estimated_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'submitted'"),
        ),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            name="fk_customer_orders_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["customer_portal_accounts.id"],
            name="fk_customer_orders_account_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_customer_orders_reviewed_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_orders_order_no",
        "customer_orders",
        ["order_no"],
        unique=True,
    )
    op.create_index(
        "customer_orders_customer_id_created_at",
        "customer_orders",
        ["customer_id", "created_at"],
    )
    op.create_index(
        "customer_orders_status_requested_date",
        "customer_orders",
        ["status", "requested_date"],
    )
    op.create_index(
        "customer_orders_requested_date_status",
        "customer_orders",
        ["requested_date", "status"],
    )
    op.create_index("customer_orders_account_id", "customer_orders", ["account_id"])
    op.create_index("customer_orders_reviewed_by", "customer_orders", ["reviewed_by"])

    op.create_table(
        "customer_order_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_account_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["customer_orders.id"],
            name="fk_customer_order_events_order_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_account_id"],
            ["customer_portal_accounts.id"],
            name="fk_customer_order_events_actor_account_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_customer_order_events_actor_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_order_events_order_id_created_at",
        "customer_order_events",
        ["order_id", "created_at"],
    )

    op.create_table(
        "customer_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_no", sa.String(length=30), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
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
            name="fk_customer_queries_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["customer_portal_accounts.id"],
            name="fk_customer_queries_account_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["users.id"],
            name="fk_customer_queries_assigned_to",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_queries_query_no",
        "customer_queries",
        ["query_no"],
        unique=True,
    )
    op.create_index(
        "customer_queries_customer_id_created_at",
        "customer_queries",
        ["customer_id", "created_at"],
    )
    op.create_index(
        "customer_queries_status_updated_at",
        "customer_queries",
        ["status", "updated_at"],
    )
    op.create_index("customer_queries_assigned_to", "customer_queries", ["assigned_to"])

    op.create_table(
        "customer_query_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_account_id", sa.Integer(), nullable=True),
        sa.Column("sender_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_internal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["query_id"],
            ["customer_queries.id"],
            name="fk_customer_query_messages_query_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_account_id"],
            ["customer_portal_accounts.id"],
            name="fk_customer_query_messages_sender_account_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name="fk_customer_query_messages_sender_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "customer_query_messages_query_id_created_at",
        "customer_query_messages",
        ["query_id", "created_at"],
    )

    op.add_column(
        "sales",
        sa.Column("source_order_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "sales_source_order_id",
        "sales",
        ["source_order_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_sales_source_order_id",
        "sales",
        "customer_orders",
        ["source_order_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sales_source_order_id", "sales", type_="foreignkey")
    op.drop_index("sales_source_order_id", table_name="sales")
    op.drop_column("sales", "source_order_id")

    op.drop_table("customer_query_messages")
    op.drop_table("customer_queries")
    op.drop_table("customer_order_events")
    op.drop_table("customer_orders")
    op.drop_table("customer_portal_account_events")
    op.drop_table("customer_portal_accounts")
