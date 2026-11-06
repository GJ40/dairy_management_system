from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base
from app.models.base import TimestampMixin


class EmailNotificationRecipient(TimestampMixin, Base):
    """An internal recipient for a category or event.

    Internal recipients are opt-in and are never mixed with the customer
    recipient of a transactional message.
    """

    __tablename__ = "email_notification_recipients"
    __table_args__ = (
        Index(
            "email_notification_recipients_mapping_key_email",
            "mapping_key",
            "email",
            unique=True,
        ),
        Index("email_notification_recipients_mapping_key", "mapping_key"),
        Index("email_notification_recipients_is_active", "is_active"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    mapping_key: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
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
            name="fk_email_notification_recipients_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_notification_recipients_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )

    @validates("email")
    def _normalize_email(self, _: str, value: str) -> str:
        return value.strip().lower()
