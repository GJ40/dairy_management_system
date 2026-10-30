from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class ExpenseCategory(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        Index("expense_categories_name", "name", unique=True),
        Index("name", "name", unique=True),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="category")

    @validates("name")
    def _normalize_name(self, _: str, value: str) -> str:
        return value.strip().lower()
