from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.repositories.expense_category_repository import ExpenseCategoryRepository
from app.repositories.expense_repository import ExpenseRepository
from app.schemas.expense import (
    UNSET,
    CreateExpenseRequest,
    ExpenseQuery,
    UpdateExpenseRequest,
    serialize_expense,
)
from app.services.security_audit_service import SecurityAuditService


def parse_expense_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Expense with id {raw_id} not found",
        )
    return int(raw_id)


class ExpenseService:
    def __init__(
        self,
        repository: ExpenseRepository,
        category_repository: ExpenseCategoryRepository,
        *,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.category_repository = category_repository
        self.audit = audit

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int | None,
        context: RequestContext | None,
        expense_id: int,
        metadata: dict[str, object],
    ) -> None:
        if self.audit is None or actor_user_id is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type="expense",
            resource_id=expense_id,
            metadata=metadata,
        )

    async def list_expenses(self, query: ExpenseQuery) -> dict[str, Any]:
        rows, total, total_amount = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            category_id=query.category_id,
            from_date=query.from_date,
            to_date=query.to_date,
        )
        total_pages = math.ceil(total / query.page_size) or 1
        return {
            "items": [serialize_expense(row) for row in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": total_pages,
            "total_expense_amount": f"{Decimal(str(total_amount)):.2f}",
        }

    async def get_expense(self, raw_id: str) -> dict[str, Any]:
        expense = await self.repository.get_by_id(parse_expense_id(raw_id))
        if expense is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Expense with id {raw_id} not found",
            )
        return {"expense": serialize_expense(expense)}

    async def get_expense_by_id(self, expense_id: int) -> dict[str, Any]:
        return await self.get_expense(str(expense_id))

    async def create_expense(
        self,
        payload: CreateExpenseRequest,
        user_id: int,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        category = await self.category_repository.get_by_id(payload.category_id)
        if category is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Expense category with id {payload.category_id} not found",
            )

        note = None if payload.note is UNSET else payload.note
        expense = await self.repository.create(
            category_id=payload.category_id,
            expense_date=date.fromisoformat(payload.expense_date),
            amount=Decimal(f"{payload.amount:.2f}"),
            note=note,
            recorded_by=user_id,
        )
        try:
            await self.repository.flush()
            await self._record(
                event_type="expense.created",
                actor_user_id=user_id,
                context=context,
                expense_id=expense.id,
                metadata={
                    "expense_id": expense.id,
                    "category_id": expense.category_id,
                    "expense_date": expense.expense_date,
                    "amount": expense.amount,
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        created = await self.repository.get_by_id(expense.id)
        if created is None:
            raise api_error(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "Failed to create expense",
            )
        return {"expense": serialize_expense(created)}

    async def update_expense(
        self,
        raw_id: str,
        payload: UpdateExpenseRequest,
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        expense = await self.repository.get_by_id(parse_expense_id(raw_id))
        if expense is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Expense with id {raw_id} not found",
            )

        updates: dict[str, Any] = {}
        if payload.category_id is not UNSET:
            category = await self.category_repository.get_by_id(
                payload.category_id
            )
            if category is None:
                raise api_error(
                    status.HTTP_404_NOT_FOUND,
                    "NOT_FOUND",
                    f"Expense category with id {payload.category_id} not found",
                )
            if expense.category_id != payload.category_id:
                updates["category_id"] = payload.category_id
        if payload.expense_date is not UNSET:
            expense_date = date.fromisoformat(payload.expense_date)
            if expense.expense_date != expense_date:
                updates["expense_date"] = expense_date
        if payload.amount is not UNSET:
            amount = Decimal(f"{payload.amount:.2f}")
            if expense.amount != amount:
                updates["amount"] = amount
        if payload.note is not UNSET and expense.note != payload.note:
            updates["note"] = payload.note

        await self.repository.update(expense, updates)
        try:
            if updates:
                await self._record(
                    event_type="expense.updated",
                    actor_user_id=actor_user_id,
                    context=context,
                    expense_id=expense.id,
                    metadata={
                        "expense_id": expense.id,
                        "changed_fields": list(updates),
                    },
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        updated = await self.repository.get_by_id(expense.id)
        if updated is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Expense with id {raw_id} not found",
            )
        return {"expense": serialize_expense(updated)}
