from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.buffalo import Buffalo
from app.models.milk_production import MilkProduction


class ProductionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_one(
        self,
        buffalo_id: int,
        prod_date: date,
        session: str,
    ) -> MilkProduction | None:
        statement = select(MilkProduction).where(
            MilkProduction.buffalo_id == buffalo_id,
            MilkProduction.prod_date == prod_date,
            MilkProduction.session == session,
            MilkProduction.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def list_for_date(self, prod_date: date) -> list[MilkProduction]:
        statement = select(MilkProduction).where(
            MilkProduction.prod_date == prod_date,
            MilkProduction.is_deleted.is_(False),
        )
        return list(await self.session.scalars(statement))

    async def list_for_date_with_details(
        self,
        prod_date: date,
    ) -> list[MilkProduction]:
        statement = (
            select(MilkProduction)
            .join(Buffalo)
            .options(
                joinedload(MilkProduction.buffalo),
                joinedload(MilkProduction.recorder),
            )
            .where(
                MilkProduction.prod_date == prod_date,
                MilkProduction.is_deleted.is_(False),
            )
            .order_by(Buffalo.tag_no.asc(), MilkProduction.session.asc())
        )
        result = await self.session.scalars(statement)
        return list(result.unique().all())

    async def list_for_buffalo(
        self,
        buffalo_id: int,
        from_date: date | None,
        to_date: date | None,
    ) -> list[MilkProduction]:
        conditions = [
            MilkProduction.buffalo_id == buffalo_id,
            MilkProduction.is_deleted.is_(False),
        ]
        if from_date is not None:
            conditions.append(MilkProduction.prod_date >= from_date)
        if to_date is not None:
            conditions.append(MilkProduction.prod_date <= to_date)
        statement = (
            select(MilkProduction)
            .where(*conditions)
            .order_by(
                MilkProduction.prod_date.desc(),
                MilkProduction.session.asc(),
            )
        )
        return list(await self.session.scalars(statement))

    async def aggregated_totals(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, str, Decimal]]:
        statement = (
            select(
                MilkProduction.prod_date,
                MilkProduction.session,
                func.sum(MilkProduction.litres),
            )
            .where(
                MilkProduction.prod_date >= from_date,
                MilkProduction.prod_date <= to_date,
                MilkProduction.is_deleted.is_(False),
            )
            .group_by(MilkProduction.prod_date, MilkProduction.session)
            .order_by(MilkProduction.prod_date.asc(), MilkProduction.session.asc())
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], str(row[1]), row[2]) for row in rows]

    async def create(
        self,
        *,
        buffalo_id: int,
        prod_date: date,
        session: str,
        litres: Decimal,
        recorded_by: int,
    ) -> MilkProduction:
        record = MilkProduction(
            buffalo_id=buffalo_id,
            prod_date=prod_date,
            session=session,
            litres=litres,
            recorded_by=recorded_by,
            is_deleted=False,
        )
        self.session.add(record)
        return record

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
