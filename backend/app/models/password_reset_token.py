from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import business_now_naive

# A single table serves both staff users and customer portal accounts. The
# subject is identified by (scope, subject_id), so no polymorphic FK is needed.
RESET_SCOPE_STAFF = "staff"
RESET_SCOPE_CUSTOMER = "customer"


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("password_reset_tokens_token_hash", "token_hash", unique=True),
        Index(
            "password_reset_tokens_scope_subject_id",
            "scope",
            "subject_id",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "staff" (users.id) or "customer" (customer_portal_accounts.id).
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Only the SHA-256 of the emailed token is stored, never the token itself.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now_naive,
    )
