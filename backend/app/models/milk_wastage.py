from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class MilkWastage(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "milk_wastage"
    __table_args__ = (
        Index("milk_wastage_waste_date", "waste_date"),
        Index("recorded_by", "recorded_by"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    waste_date: Mapped[date] = mapped_column(Date, nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="milk_wastage_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    recorder: Mapped["User"] = relationship(back_populates="wastage_records")
