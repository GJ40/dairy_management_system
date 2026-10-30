from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Expense(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("recorded_by", "recorded_by"),
        Index("expenses_expense_date", "expense_date"),
        Index("expenses_category_id", "category_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "expense_categories.id",
            name="expenses_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="expenses_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    category: Mapped["ExpenseCategory"] = relationship(back_populates="expenses")
    recorder: Mapped["User"] = relationship(back_populates="expense_records")
