from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.repositories.expense_category_repository import ExpenseCategoryRepository
from app.schemas.expense_category import (
    CreateExpenseCategoryRequest,
    serialize_expense_category,
)
from app.services.security_audit_service import SecurityAuditService


class ExpenseCategoryService:
    def __init__(
        self,
        repository: ExpenseCategoryRepository,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.audit = audit

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
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        existing = await self.repository.find_by_name(payload.name)
        if existing is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_CATEGORY",
                f"Expense category '{payload.name}' already exists",
            )
        category = await self.repository.create(name=payload.name)
        try:
            await self.repository.flush()
            if self.audit is not None and actor_user_id is not None:
                await self.audit.record(
                    event_type="expense_category.created",
                    context=context,
                    actor_user_id=actor_user_id,
                    resource_type="expense_category",
                    resource_id=category.id,
                    metadata={"category_id": category.id},
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return {"category": serialize_expense_category(category)}
