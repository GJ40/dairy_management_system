from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class CustomerQuery(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer_queries"
    __table_args__ = (
        Index("customer_queries_query_no", "query_no", unique=True),
        Index("customer_queries_customer_id_created_at", "customer_id", "created_at"),
        Index("customer_queries_status_updated_at", "status", "updated_at"),
        Index("customer_queries_assigned_to", "assigned_to"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_no: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customers.id",
            name="fk_customer_queries_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customer_portal_accounts.id",
            name="fk_customer_queries_account_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        server_default=text("'open'"),
    )
    assigned_to: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_customer_queries_assigned_to",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
