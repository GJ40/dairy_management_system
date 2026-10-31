"""Add session token version columns.

Revision ID: 0004_token_version
Revises: 0003_password_reset
Create Date: 2026-10-31

A password reset or a deactivation only takes effect on existing sessions if
issued tokens can be told apart from newer ones. Each subject keeps a counter:
tokens carry the value they were signed with, and a mismatch means the session
predates the change and must be rejected. Existing rows start at 0, which keeps
already-issued tokens valid until their own expiry.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_token_version"
down_revision: Union[str, Sequence[str], None] = "0003_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("users", "customer_portal_accounts")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "token_version")
