from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.time import business_now_naive


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now_naive,
        onupdate=business_now_naive,
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
