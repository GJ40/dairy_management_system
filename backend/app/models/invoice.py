from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Invoice(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("invoice_no", "invoice_no", unique=True),
        Index("invoices_invoice_no", "invoice_no", unique=True),
        Index("invoices_customer_id", "customer_id"),
        Index("invoices_period_start_period_end", "period_start", "period_end"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(60), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "customers.id",
            name="invoices_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unpaid",
        server_default=text("'unpaid'"),
    )

    customer: Mapped["Customer"] = relationship(back_populates="invoices")
    sale_links: Mapped[list["InvoiceSale"]] = relationship(back_populates="invoice")
