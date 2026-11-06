"""Add database-managed email and notification settings.

Revision ID: 0007_email_notification_settings
Revises: 0006_login_lockout
Create Date: 2026-11-06

Adds four additive tables:

* ``email_smtp_profiles``        - draft/active/archived SMTP transports
* ``email_sender_identities``    - selectable ``From`` identities
* ``email_workflow_mappings``    - application/category/event sender overrides
* ``email_notification_recipients`` - opt-in internal recipients

No existing table is altered. Exactly one SMTP profile may be active, enforced
by the unique ``active_slot`` index; MySQL permits multiple ``NULL`` values, so
drafts and archived rows are unaffected.

Credentials are stored as ciphertext columns and are never selected by the
settings read models.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from app.db.migration_helpers import (
    create_index_if_missing,
    create_table_if_missing,
    drop_table_if_exists,
)

revision: str = "0007_email_notification_settings"
down_revision: Union[str, Sequence[str], None] = "0006_login_lockout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    create_table_if_missing(
        "email_smtp_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider_mode", sa.String(length=20), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("auth_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("username_encrypted", sa.Text(), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "encryption_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column(
            "timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("10")
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("tested_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "last_test_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'never'"),
        ),
        sa.Column("last_test_kind", sa.String(length=20), nullable=True),
        sa.Column("last_test_reason", sa.String(length=64), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_email_smtp_profiles_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_email_smtp_profiles_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    create_index_if_missing(
        "email_smtp_profiles_active_slot",
        "email_smtp_profiles",
        ["active_slot"],
        unique=True,
    )
    create_index_if_missing(
        "email_smtp_profiles_status",
        "email_smtp_profiles",
        ["status"],
    )
    create_index_if_missing(
        "email_smtp_profiles_updated_at",
        "email_smtp_profiles",
        ["updated_at"],
    )

    create_table_if_missing(
        "email_sender_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("reply_to_email", sa.String(length=150), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_email_sender_identities_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_email_sender_identities_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    create_index_if_missing(
        "email_sender_identities_email",
        "email_sender_identities",
        ["email"],
        unique=True,
    )
    create_index_if_missing(
        "email_sender_identities_is_active",
        "email_sender_identities",
        ["is_active"],
    )

    create_table_if_missing(
        "email_workflow_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("mapping_key", sa.String(length=100), nullable=False),
        sa.Column("sender_identity_id", sa.Integer(), nullable=True),
        sa.Column("reply_to_sender_identity_id", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sender_identity_id"],
            ["email_sender_identities.id"],
            name="fk_email_workflow_mappings_sender_identity_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_sender_identity_id"],
            ["email_sender_identities.id"],
            name="fk_email_workflow_mappings_reply_to_sender_identity_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_email_workflow_mappings_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_email_workflow_mappings_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    create_index_if_missing(
        "email_workflow_mappings_mapping_key",
        "email_workflow_mappings",
        ["mapping_key"],
        unique=True,
    )
    create_index_if_missing(
        "email_workflow_mappings_scope",
        "email_workflow_mappings",
        ["scope"],
    )
    create_index_if_missing(
        "email_workflow_mappings_sender_identity_id",
        "email_workflow_mappings",
        ["sender_identity_id"],
    )
    create_index_if_missing(
        "email_workflow_mappings_reply_to_sender_identity_id",
        "email_workflow_mappings",
        ["reply_to_sender_identity_id"],
    )

    create_table_if_missing(
        "email_notification_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("mapping_key", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_email_notification_recipients_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_email_notification_recipients_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    create_index_if_missing(
        "email_notification_recipients_mapping_key_email",
        "email_notification_recipients",
        ["mapping_key", "email"],
        unique=True,
    )
    create_index_if_missing(
        "email_notification_recipients_mapping_key",
        "email_notification_recipients",
        ["mapping_key"],
    )
    create_index_if_missing(
        "email_notification_recipients_is_active",
        "email_notification_recipients",
        ["is_active"],
    )


def downgrade() -> None:
    drop_table_if_exists("email_notification_recipients")
    drop_table_if_exists("email_workflow_mappings")
    drop_table_if_exists("email_smtp_profiles")
    drop_table_if_exists("email_sender_identities")
