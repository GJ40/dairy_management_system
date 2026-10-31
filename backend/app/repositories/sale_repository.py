from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.sale import Sale


class SaleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, sale_id: int) -> Sale | None:
        statement = (
            select(Sale)
            .options(
                joinedload(Sale.customer),
                joinedload(Sale.recorder),
            )
            .where(
                Sale.id == sale_id,
                Sale.is_deleted.is_(False),
            )
        )
        result = await self.session.scalars(statement)
        return result.unique().one_or_none()

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: int | None = None,
        sale_date: date | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        payment_status: str | None = None,
    ) -> tuple[list[Sale], int]:
        conditions = [Sale.is_deleted.is_(False)]
        if customer_id is not None:
            conditions.append(Sale.customer_id == customer_id)
        if sale_date is not None:
            conditions.append(Sale.sale_date == sale_date)
        elif from_date is not None and to_date is not None:
            conditions.append(Sale.sale_date >= from_date)
            conditions.append(Sale.sale_date <= to_date)
        elif from_date is not None:
            conditions.append(Sale.sale_date >= from_date)
        elif to_date is not None:
            conditions.append(Sale.sale_date <= to_date)
        if payment_status is not None:
            conditions.append(Sale.payment_status == payment_status)

        count_statement = select(func.count()).select_from(Sale).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(Sale)
            .options(
                joinedload(Sale.customer),
                joinedload(Sale.recorder),
            )
            .where(*conditions)
            .order_by(
                Sale.sale_date.desc(),
                Sale.created_at.desc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = list((await self.session.scalars(statement)).unique().all())
        return rows, total

    async def find_by_ids_for_customer(
        self,
        customer_id: int,
        sale_ids: list[int],
    ) -> list[Sale]:
        statement = (
            select(Sale)
            .where(
                Sale.id.in_(sale_ids),
                Sale.customer_id == customer_id,
                Sale.is_deleted.is_(False),
            )
            .order_by(Sale.id.asc())
        )
        return list(await self.session.scalars(statement))

    async def find_for_period(
        self,
        *,
        customer_id: int,
        period_start: date,
        period_end: date,
    ) -> list[Sale]:
        statement = (
            select(Sale)
            .where(
                Sale.customer_id == customer_id,
                Sale.sale_date >= period_start,
                Sale.sale_date <= period_end,
                Sale.is_deleted.is_(False),
            )
            .order_by(Sale.sale_date.asc(), Sale.id.asc())
        )
        return list(await self.session.scalars(statement))

    async def create(
        self,
        *,
        customer_id: int,
        sale_date: date,
        litres: Decimal,
        rate: Decimal,
        amount: Decimal,
        recorded_by: int,
        source_order_id: int | None = None,
    ) -> Sale:
        sale = Sale(
            customer_id=customer_id,
            sale_date=sale_date,
            litres=litres,
            rate=rate,
            amount=amount,
            payment_status="unpaid",
            recorded_by=recorded_by,
            source_order_id=source_order_id,
            is_deleted=False,
        )
        self.session.add(sale)
        return sale

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
