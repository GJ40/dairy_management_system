from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("email", "email", unique=True),
        Index("users_email", "email", unique=True),
        Index("username", "username", unique=True),
        Index("users_username", "username", unique=True),
        Index("users_lock_reason", "lock_reason"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="operator",
        server_default=text("'operator'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    # Bumped whenever existing sessions must stop working (password reset,
    # deactivation). Tokens carry the value they were issued with.
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    # Failed-login lockout state. `failed_login_count` counts the current burst
    # inside `failed_login_first_at`'s window and resets on success or unlock.
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    failed_login_first_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lock_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)

    production_records: Mapped[list["MilkProduction"]] = relationship(
        back_populates="recorder"
    )
    wastage_records: Mapped[list["MilkWastage"]] = relationship(
        back_populates="recorder"
    )
    sale_records: Mapped[list["Sale"]] = relationship(back_populates="recorder")
    expense_records: Mapped[list["Expense"]] = relationship(back_populates="recorder")

    @validates("email")
    def _normalize_email(self, _: str, value: str) -> str:
        return value.strip().lower()
