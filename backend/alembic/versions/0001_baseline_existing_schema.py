"""Baseline existing MySQL schema.

This revision intentionally contains no DDL. The ten application tables already exist and were
created by the Node/Sequelize backend. After the baseline is approved, `alembic stamp` will record
this revision without modifying the schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-28

"""
from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
