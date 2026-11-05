"""Add failed-login cooldown and lockout state.

Revision ID: 0006_login_lockout
Revises: 0005_security_audit_events
Create Date: 2026-11-04

Both staff users and customer portal accounts gain the same four columns:

* ``failed_login_count``      - failures in the current burst
* ``failed_login_first_at``   - start of the burst window (UTC-naive)
* ``locked_at``               - set when the account is restricted
* ``lock_reason``             - ``failed_login_attempts`` for an automatic
                                lock, ``admin`` for an administrative one

Existing rows start unlocked with a zero counter, so the migration is safe to
run on a live table.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from app.db.migration_helpers import (
    add_column_if_missing,
    create_index_if_missing,
    drop_column_if_exists,
    drop_index_if_exists,
)

revision: str = "0006_login_lockout"
down_revision: Union[str, Sequence[str], None] = "0005_security_audit_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("users", "customer_portal_accounts")


def upgrade() -> None:
    for table in TABLES:
        add_column_if_missing(
            table,
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        add_column_if_missing(
            table,
            sa.Column("failed_login_first_at", sa.DateTime(), nullable=True),
        )
        add_column_if_missing(
            table,
            sa.Column("locked_at", sa.DateTime(), nullable=True),
        )
        add_column_if_missing(
            table,
            sa.Column("lock_reason", sa.String(length=40), nullable=True),
        )
        create_index_if_missing(f"{table}_lock_reason", table, ["lock_reason"])


def downgrade() -> None:
    for table in TABLES:
        drop_index_if_exists(f"{table}_lock_reason", table)
        drop_column_if_exists(table, "lock_reason")
        drop_column_if_exists(table, "locked_at")
        drop_column_if_exists(table, "failed_login_first_at")
        drop_column_if_exists(table, "failed_login_count")
