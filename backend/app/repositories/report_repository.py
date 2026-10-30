from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.models.milk_production import MilkProduction
from app.models.sale import Sale


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sales_in_range(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, Decimal, Decimal]]:
        statement = (
            select(Sale.sale_date, Sale.amount, Sale.litres)
            .where(
                Sale.sale_date >= from_date,
                Sale.sale_date <= to_date,
                Sale.is_deleted.is_(False),
            )
            .order_by(Sale.sale_date.asc(), Sale.id.asc())
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], row[1], row[2]) for row in rows]

    async def expense_rows_in_range(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, Decimal, str | None]]:
        statement = (
            select(Expense.expense_date, Expense.amount, ExpenseCategory.name)
            .outerjoin(
                ExpenseCategory,
                Expense.category_id == ExpenseCategory.id,
            )
            .where(
                Expense.expense_date >= from_date,
                Expense.expense_date <= to_date,
                Expense.is_deleted.is_(False),
            )
            .order_by(Expense.id.asc())
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], row[1], row[2]) for row in rows]

    async def sales_totals_for_date(
        self,
        sale_date: date,
    ) -> tuple[int, Decimal, Decimal]:
        statement = (
            select(
                func.count(),
                func.coalesce(func.sum(Sale.litres), Decimal("0")),
                func.coalesce(func.sum(Sale.amount), Decimal("0")),
            )
            .select_from(Sale)
            .where(
                Sale.sale_date == sale_date,
                Sale.is_deleted.is_(False),
            )
        )
        row = (await self.session.execute(statement)).one()
        return int(row[0] or 0), row[1], row[2]

    async def sales_amount_total(
        self,
        from_date: date,
        to_date: date,
    ) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(Sale.amount), Decimal("0")))
            .select_from(Sale)
            .where(
                Sale.sale_date >= from_date,
                Sale.sale_date <= to_date,
                Sale.is_deleted.is_(False),
            )
        )
        return await self.session.scalar(statement) or Decimal("0")

    async def expense_amount_total(
        self,
        from_date: date,
        to_date: date,
    ) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(Expense.amount), Decimal("0")))
            .select_from(Expense)
            .where(
                Expense.expense_date >= from_date,
                Expense.expense_date <= to_date,
                Expense.is_deleted.is_(False),
            )
        )
        return await self.session.scalar(statement) or Decimal("0")

    async def production_totals_for_date(
        self,
        prod_date: date,
    ) -> list[tuple[str, Decimal]]:
        statement = (
            select(
                MilkProduction.session,
                func.coalesce(func.sum(MilkProduction.litres), Decimal("0")),
            )
            .where(
                MilkProduction.prod_date == prod_date,
                MilkProduction.is_deleted.is_(False),
            )
            .group_by(MilkProduction.session)
        )
        rows = (await self.session.execute(statement)).all()
        return [(str(row[0]), row[1]) for row in rows]
