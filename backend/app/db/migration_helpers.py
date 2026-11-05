"""Idempotent DDL helpers for the Alembic revisions.

The same revision chain has to survive three very different starting points:

* a brand-new MySQL volume created by ``docker compose up`` (no tables at all),
* the legacy Sequelize database, whose tables already exist but whose
  ``alembic_version`` row may be missing (for example after ``down -v`` was
  skipped and the old volume was reattached),
* a database left behind by an interrupted ``alembic upgrade``.

``CREATE TABLE``, ``ALTER TABLE ... ADD COLUMN`` and ``CREATE INDEX`` are not
idempotent on MySQL: a second run aborts with "table already exists",
"duplicate column name" or "duplicate key name", which is exactly what made
``docker compose`` fail on an already-populated volume. Every migration
therefore probes the live schema before issuing DDL.

The probes live here so a migration never has to import another migration
file (the previous workaround re-ran ``0001`` from inside ``0002`` and
duplicated the baseline DDL). They only use reflection, so they do not depend
on application models.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import context, op


def _inspector() -> sa.Inspector:
    """A fresh inspector: DDL issued by the current migration must be visible."""
    return sa.inspect(op.get_bind())


def has_table(table: str) -> bool:
    # `alembic upgrade --sql` has no connection to inspect. Assume an empty
    # database so the generated script matches a fresh docker compose volume.
    if context.is_offline_mode():
        return False
    return _inspector().has_table(table)


def has_column(table: str, column: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(col["name"] == column for col in _inspector().get_columns(table))


def has_index(table: str, index: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(idx["name"] == index for idx in _inspector().get_indexes(table))


def has_foreign_key(table: str, name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(fk.get("name") == name for fk in _inspector().get_foreign_keys(table))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def create_table_if_missing(name: str, *args: Any, **kwargs: Any) -> None:
    if has_table(name):
        return
    op.create_table(name, *args, **kwargs)


def create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    **kwargs: Any,
) -> None:
    if has_index(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, **kwargs)


def add_column_if_missing(table_name: str, column: Any, **kwargs: Any) -> None:
    if has_column(table_name, column.name):
        return
    op.add_column(table_name, column, **kwargs)


def create_foreign_key_if_missing(
    name: str,
    source_table: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
    **kwargs: Any,
) -> None:
    if has_foreign_key(source_table, name):
        return
    op.create_foreign_key(
        name,
        source_table,
        referent_table,
        local_cols,
        remote_cols,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Drop (used by downgrades, which must also tolerate a half-applied revision)
# ---------------------------------------------------------------------------
def drop_table_if_exists(name: str) -> None:
    if context.is_offline_mode() or has_table(name):
        op.drop_table(name)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if context.is_offline_mode() or has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def drop_index_if_exists(index_name: str, table_name: str) -> None:
    if context.is_offline_mode() or has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def drop_foreign_key_if_exists(name: str, table_name: str) -> None:
    if context.is_offline_mode() or has_foreign_key(table_name, name):
        op.drop_constraint(name, table_name, type_="foreignkey")
