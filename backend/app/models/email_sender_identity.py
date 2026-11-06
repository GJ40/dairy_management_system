from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base
from app.models.base import TimestampMixin


class EmailSenderIdentity(TimestampMixin, Base):
    """A ``From`` identity that workflow mappings can reference.

    ``reply_to_email`` is independent of the visible sender address and is only
    used when no event or category mapping provides a stronger Reply-To.
    """

    __tablename__ = "email_sender_identities"
    __table_args__ = (
        Index("email_sender_identities_email", "email", unique=True),
        Index("email_sender_identities_is_active", "is_active"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    reply_to_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_sender_identities_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_sender_identities_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )

    @validates("email", "reply_to_email")
    def _normalize_email(self, _: str, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()
