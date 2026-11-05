"""Add customer portal tables.

Revision ID: 0002_customer_portal
Revises: 0001_baseline
Create Date: 2026-10-30

"""
from typing import Sequence, Union

import sqlalchemy as sa

from app.db.migration_helpers import (
    add_column_if_missing,
    create_foreign_key_if_missing,
    create_index_if_missing,
    create_table_if_missing,
    drop_column_if_exists,
    drop_foreign_key_if_exists,
    drop_index_if_exists,
    drop_table_if_exists,
)

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
    create_table_if_missing(
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
    create_index_if_missing(
        "customer_portal_accounts_customer_id",
        "customer_portal_accounts",
        ["customer_id"],
        unique=True,
    )
    create_index_if_missing(
        "customer_portal_accounts_email",
        "customer_portal_accounts",
        ["email"],
        unique=True,
    )
    create_index_if_missing(
        "customer_portal_accounts_is_active",
        "customer_portal_accounts",
        ["is_active"],
    )

    create_table_if_missing(
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
    create_index_if_missing(
        "customer_portal_account_events_account_id_created_at",
        "customer_portal_account_events",
        ["account_id", "created_at"],
    )

    create_table_if_missing(
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
    create_index_if_missing(
        "customer_orders_order_no",
        "customer_orders",
        ["order_no"],
        unique=True,
    )
    create_index_if_missing(
        "customer_orders_customer_id_created_at",
        "customer_orders",
        ["customer_id", "created_at"],
    )
    create_index_if_missing(
        "customer_orders_status_requested_date",
        "customer_orders",
        ["status", "requested_date"],
    )
    create_index_if_missing(
        "customer_orders_requested_date_status",
        "customer_orders",
        ["requested_date", "status"],
    )
    create_index_if_missing("customer_orders_account_id", "customer_orders", ["account_id"])
    create_index_if_missing("customer_orders_reviewed_by", "customer_orders", ["reviewed_by"])

    create_table_if_missing(
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
    create_index_if_missing(
        "customer_order_events_order_id_created_at",
        "customer_order_events",
        ["order_id", "created_at"],
    )

    create_table_if_missing(
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
    create_index_if_missing(
        "customer_queries_query_no",
        "customer_queries",
        ["query_no"],
        unique=True,
    )
    create_index_if_missing(
        "customer_queries_customer_id_created_at",
        "customer_queries",
        ["customer_id", "created_at"],
    )
    create_index_if_missing(
        "customer_queries_status_updated_at",
        "customer_queries",
        ["status", "updated_at"],
    )
    create_index_if_missing("customer_queries_assigned_to", "customer_queries", ["assigned_to"])

    create_table_if_missing(
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
    create_index_if_missing(
        "customer_query_messages_query_id_created_at",
        "customer_query_messages",
        ["query_id", "created_at"],
    )

    add_column_if_missing(
        "sales",
        sa.Column("source_order_id", sa.Integer(), nullable=True),
    )
    create_index_if_missing(
        "sales_source_order_id",
        "sales",
        ["source_order_id"],
        unique=True,
    )
    create_foreign_key_if_missing(
        "fk_sales_source_order_id",
        "sales",
        "customer_orders",
        ["source_order_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    drop_foreign_key_if_exists("fk_sales_source_order_id", "sales")
    drop_index_if_exists("sales_source_order_id", "sales")
    drop_column_if_exists("sales", "source_order_id")

    drop_table_if_exists("customer_query_messages")
    drop_table_if_exists("customer_queries")
    drop_table_if_exists("customer_order_events")
    drop_table_if_exists("customer_orders")
    drop_table_if_exists("customer_portal_account_events")
    drop_table_if_exists("customer_portal_accounts")
