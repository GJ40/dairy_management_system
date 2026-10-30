from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class MilkProduction(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "milk_production"
    __table_args__ = (
        Index(
            "milk_production_buffalo_id_prod_date_session",
            "buffalo_id",
            "prod_date",
            "session",
            unique=True,
        ),
        Index("milk_production_prod_date", "prod_date"),
        Index("milk_production_buffalo_id_prod_date", "buffalo_id", "prod_date"),
        Index("recorded_by", "recorded_by"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buffalo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "buffaloes.id",
            name="milk_production_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    prod_date: Mapped[date] = mapped_column(Date, nullable=False)
    session: Mapped[str] = mapped_column(String(20), nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    recorded_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="milk_production_ibfk_2",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    buffalo: Mapped["Buffalo"] = relationship(back_populates="production_records")
    recorder: Mapped["User"] = relationship(back_populates="production_records")
