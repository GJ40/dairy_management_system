from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class InvoiceSale(TimestampMixin, Base):
    __tablename__ = "invoice_sales"
    __table_args__ = (
        Index(
            "invoice_sales_sale_id_invoice_id_unique",
            "invoice_id",
            "sale_id",
            unique=True,
        ),
        Index("invoice_sales_sale_id", "sale_id", unique=True),
        Index("invoice_sales_invoice_id", "invoice_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "invoices.id",
            name="invoice_sales_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sale_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "sales.id",
            name="invoice_sales_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="sale_links")
    sale: Mapped["Sale"] = relationship(back_populates="invoice_links")
