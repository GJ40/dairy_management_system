from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.expense import Expense


class ExpenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, expense_id: int) -> Expense | None:
        statement = (
            select(Expense)
            .options(
                joinedload(Expense.category),
                joinedload(Expense.recorder),
            )
            .where(
                Expense.id == expense_id,
                Expense.is_deleted.is_(False),
            )
        )
        result = await self.session.scalars(statement)
        return result.unique().one_or_none()

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        category_id: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> tuple[list[Expense], int, Decimal]:
        conditions = [Expense.is_deleted.is_(False)]
        if category_id is not None:
            conditions.append(Expense.category_id == category_id)
        start = date.fromisoformat(from_date) if from_date is not None else None
        end = date.fromisoformat(to_date) if to_date is not None else None
        if start is not None and end is not None:
            conditions.append(Expense.expense_date >= start)
            conditions.append(Expense.expense_date <= end)
        elif start is not None:
            conditions.append(Expense.expense_date >= start)
        elif end is not None:
            conditions.append(Expense.expense_date <= end)

        count_statement = select(func.count()).select_from(Expense).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        total_statement = (
            select(func.coalesce(func.sum(Expense.amount), Decimal("0")))
            .select_from(Expense)
            .where(*conditions)
        )
        total_amount = await self.session.scalar(total_statement)
        if total_amount is None:
            total_amount = Decimal("0")

        statement = (
            select(Expense)
            .options(
                joinedload(Expense.category),
                joinedload(Expense.recorder),
            )
            .where(*conditions)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = list((await self.session.scalars(statement)).unique().all())
        return rows, total, Decimal(str(total_amount))

    async def create(
        self,
        *,
        category_id: int,
        expense_date: date,
        amount: Decimal,
        note: str | None,
        recorded_by: int,
    ) -> Expense:
        expense = Expense(
            category_id=category_id,
            expense_date=expense_date,
            amount=amount,
            note=note,
            recorded_by=recorded_by,
            is_deleted=False,
        )
        self.session.add(expense)
        return expense

    async def update(self, expense: Expense, updates: dict[str, Any]) -> Expense:
        for key, value in updates.items():
            setattr(expense, key, value)
        return expense

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
