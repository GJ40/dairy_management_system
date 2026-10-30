from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.repositories.expense_category_repository import ExpenseCategoryRepository
from app.schemas.expense_category import (
    CreateExpenseCategoryRequest,
    serialize_expense_category,
)


class ExpenseCategoryService:
    def __init__(self, repository: ExpenseCategoryRepository) -> None:
        self.repository = repository

    async def list_categories(self) -> dict[str, Any]:
        categories = await self.repository.list_active()
        return {
            "categories": [
                serialize_expense_category(category) for category in categories
            ]
        }

    async def create_category(
        self,
        payload: CreateExpenseCategoryRequest,
    ) -> dict[str, Any]:
        existing = await self.repository.find_by_name(payload.name)
        if existing is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_CATEGORY",
                f"Expense category '{payload.name}' already exists",
            )
        category = await self.repository.create(name=payload.name)
        return {"category": serialize_expense_category(category)}
