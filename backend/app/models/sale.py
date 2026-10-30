from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Sale(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (
        Index("recorded_by", "recorded_by"),
        Index("sales_sale_date", "sale_date"),
        Index("sales_customer_id_sale_date", "customer_id", "sale_date"),
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
            name="sales_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unpaid",
        server_default=text("'unpaid'"),
    )
    recorded_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="sales_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship(back_populates="sales")
    recorder: Mapped["User"] = relationship(back_populates="sale_records")
    invoice_links: Mapped[list["InvoiceSale"]] = relationship(back_populates="sale")
