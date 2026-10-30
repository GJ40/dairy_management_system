from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milk_production import MilkProduction
from app.models.milk_wastage import MilkWastage
from app.models.sale import Sale


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class StockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _sum(
        self,
        model: Any,
        date_column: Any,
        value: date,
        *,
        before: bool,
    ) -> Decimal:
        condition = date_column < value if before else date_column == value
        statement = select(func.sum(model.litres)).where(
            condition,
            model.is_deleted.is_(False),
        )
        return _decimal(await self.session.scalar(statement))

    async def sum_prior_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        production = await self._sum(
            MilkProduction,
            MilkProduction.prod_date,
            stock_date,
            before=True,
        )
        sales = await self._sum(
            Sale,
            Sale.sale_date,
            stock_date,
            before=True,
        )
        wastage = await self._sum(
            MilkWastage,
            MilkWastage.waste_date,
            stock_date,
            before=True,
        )
        return production, sales, wastage

    async def sum_current_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        production = await self._sum(
            MilkProduction,
            MilkProduction.prod_date,
            stock_date,
            before=False,
        )
        sales = await self._sum(
            Sale,
            Sale.sale_date,
            stock_date,
            before=False,
        )
        wastage = await self._sum(
            MilkWastage,
            MilkWastage.waste_date,
            stock_date,
            before=False,
        )
        return production, sales, wastage

    async def get_future_active_dates(self, stock_date: date) -> list[date]:
        dates: set[date] = set()
        statements = (
            select(MilkProduction.prod_date).where(
                MilkProduction.prod_date > stock_date,
                MilkProduction.is_deleted.is_(False),
            ),
            select(Sale.sale_date).where(
                Sale.sale_date > stock_date,
                Sale.is_deleted.is_(False),
            ),
            select(MilkWastage.waste_date).where(
                MilkWastage.waste_date > stock_date,
                MilkWastage.is_deleted.is_(False),
            ),
        )
        for statement in statements:
            dates.update(await self.session.scalars(statement))
        return sorted(dates)
