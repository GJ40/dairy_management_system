from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import business_now_naive


class CustomerQueryMessage(Base):
    __tablename__ = "customer_query_messages"
    __table_args__ = (
        Index("customer_query_messages_query_id_created_at", "query_id", "created_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customer_queries.id",
            name="fk_customer_query_messages_query_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "customer_portal_accounts.id",
            name="fk_customer_query_messages_sender_account_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    sender_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_customer_query_messages_sender_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now_naive,
    )
