"""Add the centralized security audit ledger.

Revision ID: 0005_security_audit_events
Revises: 0004_token_version
Create Date: 2026-11-04

The table is append-only: there is no updated_at, soft-delete column or
update/delete API. New rows use UTC-naive timestamps so security events are
not mixed with the existing Asia/Kolkata business timestamps.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.db.migration_helpers import (
    create_index_if_missing,
    create_table_if_missing,
    drop_table_if_exists,
)

revision: str = "0005_security_audit_events"
down_revision: Union[str, Sequence[str], None] = "0004_token_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    create_table_if_missing(
        "security_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_account_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("http_method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_security_audit_events_actor_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_account_id"],
            ["customer_portal_accounts.id"],
            name="fk_security_audit_events_actor_account_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    create_index_if_missing(
        "security_audit_events_created_at",
        "security_audit_events",
        ["created_at"],
    )
    create_index_if_missing(
        "security_audit_events_event_type_created_at",
        "security_audit_events",
        ["event_type", "created_at"],
    )
    create_index_if_missing(
        "security_audit_events_actor_user_id_created_at",
        "security_audit_events",
        ["actor_user_id", "created_at"],
    )
    create_index_if_missing(
        "security_audit_events_actor_account_id_created_at",
        "security_audit_events",
        ["actor_account_id", "created_at"],
    )
    create_index_if_missing(
        "security_audit_events_request_id",
        "security_audit_events",
        ["request_id"],
    )
    create_index_if_missing(
        "security_audit_events_resource_created_at",
        "security_audit_events",
        ["resource_type", "resource_id", "created_at"],
    )
    create_index_if_missing(
        "security_audit_events_ip_created_at",
        "security_audit_events",
        ["ip_address", "created_at"],
    )


def downgrade() -> None:
    drop_table_if_exists("security_audit_events")
