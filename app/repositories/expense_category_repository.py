from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense_category import ExpenseCategory


class ExpenseCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, category_id: int) -> ExpenseCategory | None:
        statement = select(ExpenseCategory).where(
            ExpenseCategory.id == category_id,
            ExpenseCategory.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def list_active(self) -> list[ExpenseCategory]:
        statement = (
            select(ExpenseCategory)
            .where(ExpenseCategory.is_deleted.is_(False))
            .order_by(ExpenseCategory.name.asc())
        )
        return list(await self.session.scalars(statement))

    async def find_by_name(self, name: str) -> ExpenseCategory | None:
        statement = select(ExpenseCategory).where(
            ExpenseCategory.name == name,
            ExpenseCategory.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def create(self, *, name: str) -> ExpenseCategory:
        category = ExpenseCategory(name=name)
        self.session.add(category)
        return category
