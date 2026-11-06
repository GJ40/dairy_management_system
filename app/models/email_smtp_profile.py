from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class EmailSmtpProfile(TimestampMixin, Base):
    """A database-managed SMTP transport.

    Exactly one row may be active. ``active_slot`` is ``1`` for the active row
    and ``NULL`` for every other row; the unique index relies on MySQL allowing
    multiple ``NULL`` values, so drafts and archived profiles coexist freely.

    Credentials are stored only as ciphertext. The application must never
    serialize ``username_encrypted`` or ``password_encrypted``.
    """

    __tablename__ = "email_smtp_profiles"
    __table_args__ = (
        Index("email_smtp_profiles_active_slot", "active_slot", unique=True),
        Index("email_smtp_profiles_status", "status"),
        Index("email_smtp_profiles_updated_at", "updated_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    auth_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    username_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="none",
        server_default=text("'none'"),
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default=text("10"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    tested_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_test_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="never",
        server_default=text("'never'"),
    )
    last_test_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_smtp_profiles_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_smtp_profiles_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
