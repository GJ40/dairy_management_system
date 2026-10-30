from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class CustomerOrder(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer_orders"
    __table_args__ = (
        Index("customer_orders_order_no", "order_no", unique=True),
        Index("customer_orders_customer_id_created_at", "customer_id", "created_at"),
        Index("customer_orders_status_requested_date", "status", "requested_date"),
        Index("customer_orders_requested_date_status", "requested_date", "status"),
        Index("customer_orders_account_id", "account_id"),
        Index("customer_orders_reviewed_by", "reviewed_by"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customers.id",
            name="fk_customer_orders_customer_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customer_portal_accounts.id",
            name="fk_customer_orders_account_id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="submitted",
        server_default=text("'submitted'"),
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_customer_orders_reviewed_by",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
