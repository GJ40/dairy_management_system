from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class EmailWorkflowMapping(TimestampMixin, Base):
    """Sender/Reply-To override at application, category or event scope.

    ``mapping_key`` is validated against the code-owned workflow catalogue by
    the service layer; the database only enforces uniqueness.
    """

    __tablename__ = "email_workflow_mappings"
    __table_args__ = (
        Index("email_workflow_mappings_mapping_key", "mapping_key", unique=True),
        Index("email_workflow_mappings_scope", "scope"),
        Index("email_workflow_mappings_sender_identity_id", "sender_identity_id"),
        Index(
            "email_workflow_mappings_reply_to_sender_identity_id",
            "reply_to_sender_identity_id",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    mapping_key: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_identity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "email_sender_identities.id",
            name="fk_email_workflow_mappings_sender_identity_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    reply_to_sender_identity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "email_sender_identities.id",
            name="fk_email_workflow_mappings_reply_to_sender_identity_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_workflow_mappings_created_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_email_workflow_mappings_updated_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
