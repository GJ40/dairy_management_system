from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.milk_wastage import MilkWastage


class WastageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        waste_date: date,
        litres: Decimal,
        reason: str,
        recorded_by: int,
    ) -> MilkWastage:
        record = MilkWastage(
            waste_date=waste_date,
            litres=litres,
            reason=reason,
            recorded_by=recorded_by,
            is_deleted=False,
        )
        self.session.add(record)
        return record

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        waste_date: date | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        reason: str | None = None,
    ) -> tuple[int, list[MilkWastage]]:
        conditions = [MilkWastage.is_deleted.is_(False)]
        if waste_date is not None:
            conditions.append(MilkWastage.waste_date == waste_date)
        elif from_date is not None and to_date is not None:
            conditions.append(MilkWastage.waste_date >= from_date)
            conditions.append(MilkWastage.waste_date <= to_date)
        elif from_date is not None:
            conditions.append(MilkWastage.waste_date >= from_date)
        elif to_date is not None:
            conditions.append(MilkWastage.waste_date <= to_date)

        if reason is not None:
            conditions.append(MilkWastage.reason == reason)

        count_statement = select(func.count()).select_from(MilkWastage).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(MilkWastage)
            .options(joinedload(MilkWastage.recorder))
            .where(*conditions)
            .order_by(
                MilkWastage.waste_date.desc(),
                MilkWastage.created_at.desc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = list((await self.session.scalars(statement)).unique().all())
        return total, rows

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
