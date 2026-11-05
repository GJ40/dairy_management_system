from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.user import User
from app.repositories.wastage_repository import WastageRepository
from app.schemas.wastage import (
    RecordWastageRequest,
    WastageQuery,
    serialize_wastage,
    serialize_wastage_detail,
)
from app.services.security_audit_service import SecurityAuditService
from app.services.stock_service import StockService
from app.utils.time import is_future_date, is_today


class WastageService:
    def __init__(
        self,
        repository: WastageRepository,
        stock_service: StockService,
        *,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.stock_service = stock_service
        self.audit = audit

    async def _record(
        self,
        *,
        actor_user_id: int | None,
        context: RequestContext | None,
        wastage_id: int,
        waste_date: str,
        litres: Decimal,
        reason: str,
    ) -> None:
        if self.audit is None or actor_user_id is None:
            return
        await self.audit.record(
            event_type="wastage.recorded",
            context=context,
            actor_user_id=actor_user_id,
            resource_type="milk_wastage",
            resource_id=wastage_id,
            metadata={
                "wastage_id": wastage_id,
                "waste_date": waste_date,
                "litres": litres,
                "reason": reason,
            },
        )

    def _assert_date_permission(self, waste_date: str, user: User) -> None:
        if is_future_date(waste_date):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_WASTAGE_DATE",
                "Wastage date cannot be in the future",
            )
        if user.role == "operator" and not is_today(waste_date):
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "OPERATOR_DATE_RESTRICTION",
                "Operators may only record wastage for the current business day",
            )

    async def record_wastage(
        self,
        payload: RecordWastageRequest,
        user: User,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        self._assert_date_permission(payload.waste_date, user)
        formatted_litres = Decimal(f"{payload.litres:.2f}")

        try:
            await self.stock_service.assert_available_stock(
                payload.waste_date,
                formatted_litres,
            )
            record = await self.repository.create(
                waste_date=date.fromisoformat(payload.waste_date),
                litres=formatted_litres,
                reason=payload.reason,
                recorded_by=user.id,
            )
            await self.repository.flush()
            await self._record(
                actor_user_id=user.id,
                context=context,
                wastage_id=record.id,
                waste_date=payload.waste_date,
                litres=record.litres,
                reason=record.reason,
            )
            updated_stock = await self.stock_service.get_stock_for_date(
                payload.waste_date
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return {
            "wastage": serialize_wastage(record),
            "stock_remaining": updated_stock["closing_stock"],
        }

    async def list_wastage(self, query: WastageQuery) -> dict[str, Any]:
        if (
            query.waste_date is None
            and query.from_date is not None
            and query.to_date is not None
        ):
            if query.from_date > query.to_date:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_DATE_RANGE",
                    "'from' date cannot be after 'to' date",
                )

        total, rows = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            waste_date=(
                date.fromisoformat(query.waste_date)
                if query.waste_date is not None
                else None
            ),
            from_date=(
                date.fromisoformat(query.from_date)
                if query.from_date is not None
                else None
            ),
            to_date=(
                date.fromisoformat(query.to_date)
                if query.to_date is not None
                else None
            ),
            reason=query.reason,
        )

        return {
            "items": [serialize_wastage_detail(row) for row in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
        }
