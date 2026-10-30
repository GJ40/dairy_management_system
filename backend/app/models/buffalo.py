from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Buffalo(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "buffaloes"
    __table_args__ = (
        Index("buffaloes_status", "status"),
        Index("buffaloes_tag_no", "tag_no", unique=True),
        Index("tag_no", "tag_no", unique=True),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_no: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    breed: Mapped[str] = mapped_column(String(80), nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )

    production_records: Mapped[list["MilkProduction"]] = relationship(
        back_populates="buffalo"
    )

    @validates("tag_no")
    def _normalize_tag_no(self, _: str, value: str) -> str:
        return value.strip().upper()
