from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.buffalo import Buffalo
from app.models.user import User
from app.repositories.buffalo_repository import BuffaloRepository
from app.repositories.production_repository import ProductionRepository
from app.schemas.production import (
    UNSET,
    BulkProductionRequest,
    SingleProductionRequest,
    serialize_production,
    serialize_production_detail,
)
from app.services.buffalo_service import parse_buffalo_id
from app.services.security_audit_service import SecurityAuditService
from app.utils.time import get_business_date, is_future_date, is_today


def _decimal_litres(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _integrity_message(exc: IntegrityError) -> str:
    original = getattr(exc, "orig", None)
    args = getattr(original, "args", ())
    if len(args) > 1 and isinstance(args[1], str):
        return args[1]
    return str(original or exc)


class ProductionService:
    def __init__(
        self,
        repository: ProductionRepository,
        buffalo_repository: BuffaloRepository,
        *,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.buffalo_repository = buffalo_repository
        self.audit = audit

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int | None,
        context: RequestContext | None,
        production_id: int | None,
        metadata: dict[str, object],
    ) -> None:
        if self.audit is None or actor_user_id is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type=(
                "milk_production" if production_id is not None else "milk_production_day"
            ),
            resource_id=production_id if production_id is not None else None,
            metadata=metadata,
        )

    def _assert_date_permission(self, prod_date: str, user: User) -> None:
        if is_future_date(prod_date):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PRODUCTION_DATE",
                "Production date cannot be in the future",
            )
        if user.role == "operator" and not is_today(prod_date):
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "OPERATOR_DATE_RESTRICTION",
                "Operators may only record or edit milk production for "
                "the current business day",
            )

    async def _assert_active_buffalo(self, buffalo_id: int) -> Buffalo:
        buffalo = await self.buffalo_repository.get_by_id(buffalo_id)
        if buffalo is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Buffalo with id {buffalo_id} not found",
            )
        if buffalo.status != "active":
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "BUFFALO_NOT_ACTIVE",
                f"Buffalo '{buffalo.tag_no}' is marked as '{buffalo.status}' "
                "and cannot receive production entries. Only active buffaloes "
                "are eligible.",
            )
        return buffalo

    async def record_production(
        self,
        payload: SingleProductionRequest,
        user: User,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        self._assert_date_permission(payload.prod_date, user)
        await self._assert_active_buffalo(payload.buffalo_id)

        prod_date = date.fromisoformat(payload.prod_date)
        formatted_litres = _decimal_litres(payload.litres)
        existing = await self.repository.find_one(
            payload.buffalo_id,
            prod_date,
            payload.session,
        )
        if existing is not None:
            if not payload.overwrite:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "DUPLICATE_PRODUCTION_ENTRY",
                    "A production entry already exists for buffalo id "
                    f"{payload.buffalo_id} on {payload.prod_date} "
                    f"({payload.session} session). Set overwrite: true to update.",
                )
            existing.litres = formatted_litres
            existing.recorded_by = user.id
            try:
                await self._record(
                    event_type="production.updated",
                    actor_user_id=user.id,
                    context=context,
                    production_id=existing.id,
                    metadata={
                        "production_id": existing.id,
                        "buffalo_id": existing.buffalo_id,
                        "prod_date": payload.prod_date,
                        "session_name": existing.session,
                        "litres": existing.litres,
                    },
                )
                await self.repository.commit()
            except Exception:
                await self.repository.rollback()
                raise
            return serialize_production(existing)

        record = await self.repository.create(
            buffalo_id=payload.buffalo_id,
            prod_date=prod_date,
            session=payload.session,
            litres=formatted_litres,
            recorded_by=user.id,
        )
        try:
            await self.repository.flush()
            await self._record(
                event_type="production.recorded",
                actor_user_id=user.id,
                context=context,
                production_id=record.id,
                metadata={
                    "production_id": record.id,
                    "buffalo_id": record.buffalo_id,
                    "prod_date": payload.prod_date,
                    "session_name": record.session,
                    "litres": record.litres,
                },
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                _integrity_message(exc),
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        return serialize_production(record)

    async def record_bulk_production(
        self,
        payload: BulkProductionRequest,
        user: User,
        *,
        context: RequestContext | None = None,
    ) -> list[dict[str, Any]]:
        self._assert_date_permission(payload.prod_date, user)
        prod_date = date.fromisoformat(payload.prod_date)
        saved: list[Any] = []
        created_count = 0
        updated_count = 0
        try:
            for item in payload.entries:
                buffalo = await self._assert_active_buffalo(item.buffalo_id)
                sessions: list[tuple[str, Any]] = []
                if item.morning_litres is not UNSET:
                    sessions.append(("morning", item.morning_litres))
                if item.evening_litres is not UNSET:
                    sessions.append(("evening", item.evening_litres))
                if item.session is not UNSET and item.litres is not UNSET:
                    sessions.append((item.session, item.litres))

                for session_name, litres in sessions:
                    existing = await self.repository.find_one(
                        buffalo.id,
                        prod_date,
                        session_name,
                    )
                    if existing is not None:
                        if not payload.overwrite:
                            raise api_error(
                                status.HTTP_409_CONFLICT,
                                "DUPLICATE_PRODUCTION_ENTRY",
                                "Production record already exists for "
                                f"{buffalo.tag_no} on {payload.prod_date} "
                                f"({session_name}). Use overwrite: true to "
                                "confirm update.",
                            )
                        existing.litres = _decimal_litres(litres)
                        existing.recorded_by = user.id
                        saved.append(existing)
                        updated_count += 1
                    else:
                        record = await self.repository.create(
                            buffalo_id=buffalo.id,
                            prod_date=prod_date,
                            session=session_name,
                            litres=_decimal_litres(litres),
                            recorded_by=user.id,
                        )
                        await self.repository.flush()
                        saved.append(record)
                        created_count += 1

            if saved:
                await self._record(
                    event_type="production.bulk_recorded",
                    actor_user_id=user.id,
                    context=context,
                    production_id=None,
                    metadata={
                        "prod_date": payload.prod_date,
                        "entry_count": len(saved),
                        "created_count": created_count,
                        "updated_count": updated_count,
                    },
                )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                _integrity_message(exc),
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        return [serialize_production(record) for record in saved]

    async def get_grid(self, raw_date: str | None) -> dict[str, Any]:
        grid_date = raw_date or get_business_date()
        if is_future_date(grid_date):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PRODUCTION_DATE",
                "Grid date cannot be in the future",
            )

        active_buffaloes = await self.buffalo_repository.list_active()
        productions = await self.repository.list_for_date(
            date.fromisoformat(grid_date)
        )
        prod_map: dict[int, dict[str, float]] = {}
        for record in productions:
            sessions = prod_map.setdefault(record.buffalo_id, {})
            sessions[record.session] = float(record.litres)

        herd_morning = 0.0
        herd_evening = 0.0
        rows: list[dict[str, Any]] = []
        for buffalo in active_buffaloes:
            sessions = prod_map.get(buffalo.id, {})
            morning = sessions.get("morning")
            evening = sessions.get("evening")
            if morning is not None:
                herd_morning += morning
            if evening is not None:
                herd_evening += evening
            daily_total = (
                f"{float(morning or 0) + float(evening or 0):.2f}"
                if morning is not None or evening is not None
                else None
            )
            rows.append(
                {
                    "buffalo_id": buffalo.id,
                    "tag_no": buffalo.tag_no,
                    "name": buffalo.name,
                    "breed": buffalo.breed,
                    "morning_litres": (
                        f"{morning:.2f}" if morning is not None else None
                    ),
                    "evening_litres": (
                        f"{evening:.2f}" if evening is not None else None
                    ),
                    "daily_total": daily_total,
                }
            )

        return {
            "date": grid_date,
            "active_buffaloes_count": len(active_buffaloes),
            "herd_totals": {
                "morning": f"{herd_morning:.2f}",
                "evening": f"{herd_evening:.2f}",
                "grand_total": f"{herd_morning + herd_evening:.2f}",
            },
            "grid": rows,
        }

    async def get_production_by_date(self, raw_date: str | None) -> dict[str, Any]:
        prod_date = raw_date or get_business_date()
        records = await self.repository.list_for_date_with_details(
            date.fromisoformat(prod_date)
        )
        morning = 0.0
        evening = 0.0
        for record in records:
            value = float(record.litres)
            if record.session == "morning":
                morning += value
            if record.session == "evening":
                evening += value
        return {
            "date": prod_date,
            "herd_totals": {
                "morning": f"{morning:.2f}",
                "evening": f"{evening:.2f}",
                "grand_total": f"{morning + evening:.2f}",
            },
            "entries": [
                serialize_production_detail(record) for record in records
            ],
        }

    async def get_summary(self, from_date: str, to_date: str) -> dict[str, Any]:
        if from_date > to_date:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DATE_RANGE",
                "'from' date cannot be after 'to' date",
            )

        rows = await self.repository.aggregated_totals(
            date.fromisoformat(from_date),
            date.fromisoformat(to_date),
        )
        day_map: dict[str, dict[str, Any]] = {}
        grand_total = 0.0
        for prod_date, session, total in rows:
            key = prod_date.isoformat()
            day = day_map.setdefault(
                key,
                {
                    "prod_date": key,
                    "morning": 0.0,
                    "evening": 0.0,
                    "total": 0.0,
                },
            )
            litres = float(total or 0)
            if session == "morning":
                day["morning"] = litres
            if session == "evening":
                day["evening"] = litres
            day["total"] += litres
            grand_total += litres

        daily_summaries = [
            {
                "prod_date": day["prod_date"],
                "morning_litres": f"{day['morning']:.2f}",
                "evening_litres": f"{day['evening']:.2f}",
                "total_litres": f"{day['total']:.2f}",
            }
            for day in day_map.values()
        ]
        days_recorded = len(daily_summaries)
        average = grand_total / days_recorded if days_recorded else 0.0
        return {
            "period": {"from": from_date, "to": to_date},
            "days_recorded": days_recorded,
            "grand_total_litres": f"{grand_total:.2f}",
            "average_daily_litres": f"{average:.2f}",
            "daily_summaries": daily_summaries,
        }

    async def get_buffalo_history(
        self,
        raw_id: str,
        from_date: str | None,
        to_date: str | None,
    ) -> dict[str, Any]:
        buffalo_id = parse_buffalo_id(raw_id)
        buffalo = await self.buffalo_repository.get_by_id(buffalo_id)
        if buffalo is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Buffalo with id {raw_id} not found",
            )

        if (
            from_date is not None
            and to_date is not None
            and from_date > to_date
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DATE_RANGE",
                "'from' date cannot be after 'to' date",
            )

        records = await self.repository.list_for_buffalo(
            buffalo_id,
            date.fromisoformat(from_date) if from_date is not None else None,
            date.fromisoformat(to_date) if to_date is not None else None,
        )
        day_map: dict[str, dict[str, Any]] = {}
        total_litres = 0.0
        for record in records:
            key = record.prod_date.isoformat()
            day = day_map.setdefault(
                key,
                {
                    "prod_date": key,
                    "morning": 0.0,
                    "evening": 0.0,
                    "total": 0.0,
                },
            )
            litres = float(record.litres)
            if record.session == "morning":
                day["morning"] = litres
            if record.session == "evening":
                day["evening"] = litres
            day["total"] += litres
            total_litres += litres

        days_recorded = len(day_map)
        average = total_litres / days_recorded if days_recorded else 0.0
        history = [
            {
                "prod_date": day["prod_date"],
                "morning_litres": f"{day['morning']:.2f}",
                "evening_litres": f"{day['evening']:.2f}",
                "total_litres": f"{day['total']:.2f}",
            }
            for day in day_map.values()
        ]
        return {
            "buffalo": {
                "id": buffalo.id,
                "tag_no": buffalo.tag_no,
                "name": buffalo.name,
                "breed": buffalo.breed,
                "status": buffalo.status,
            },
            "days_recorded": days_recorded,
            "total_litres_produced": f"{total_litres:.2f}",
            "average_daily_yield": f"{average:.2f}",
            "history": history,
        }
