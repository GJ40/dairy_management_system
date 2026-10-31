"""Add password reset tokens.

Revision ID: 0003_password_reset
Revises: 0002_customer_portal
Create Date: 2026-10-31

One table serves both staff users (`scope='staff'`, `users.id`) and customer
portal accounts (`scope='customer'`, `customer_portal_accounts.id`). Only the
SHA-256 of each emailed token is stored.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_password_reset"
down_revision: Union[str, Sequence[str], None] = "0002_customer_portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "password_reset_tokens_scope_subject_id",
        "password_reset_tokens",
        ["scope", "subject_id"],
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
