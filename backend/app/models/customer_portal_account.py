from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class CustomerPortalAccount(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer_portal_accounts"
    __table_args__ = (
        Index(
            "customer_portal_accounts_customer_id",
            "customer_id",
            unique=True,
        ),
        Index("customer_portal_accounts_email", "email", unique=True),
        Index("customer_portal_accounts_is_active", "is_active"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customers.id",
            name="fk_customer_portal_accounts_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    activation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activation_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
