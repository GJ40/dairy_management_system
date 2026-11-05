from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.repositories.buffalo_repository import BuffaloRepository
from app.schemas.buffalo import (
    BuffaloQuery,
    CreateBuffaloRequest,
    UpdateBuffaloRequest,
    serialize_buffalo,
)
from app.services.security_audit_service import SecurityAuditService


def parse_buffalo_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Buffalo with id {raw_id} not found",
        )
    return int(raw_id)


def _date_value(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


class BuffaloService:
    def __init__(
        self,
        repository: BuffaloRepository,
        *,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.audit = audit

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int | None,
        context: RequestContext | None,
        buffalo_id: int,
        metadata: dict[str, object],
    ) -> None:
        if self.audit is None or actor_user_id is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type="buffalo",
            resource_id=buffalo_id,
            metadata=metadata,
        )

    async def list_buffaloes(self, query: BuffaloQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_buffaloes(query)
        return {
            "items": [serialize_buffalo(buffalo) for buffalo in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
        }

    async def get_buffalo(self, raw_id: str) -> dict[str, Any]:
        buffalo_id = parse_buffalo_id(raw_id)
        buffalo = await self.repository.get_by_id(buffalo_id)
        if buffalo is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Buffalo with id {raw_id} not found",
            )
        return serialize_buffalo(buffalo)

    async def create_buffalo(
        self,
        payload: CreateBuffaloRequest,
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        normalized_tag = payload.tag_no.strip().upper()
        existing = await self.repository.get_by_tag_no(normalized_tag)
        if existing is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                f"Buffalo with tag number '{normalized_tag}' already exists",
            )

        buffalo = await self.repository.create(
            tag_no=normalized_tag,
            name=payload.name.strip(),
            breed=payload.breed.strip(),
            dob=_date_value(payload.dob),
            purchase_date=_date_value(payload.purchase_date),
            status=payload.status,
        )
        try:
            await self.repository.flush()
            await self._record(
                event_type="buffalo.created",
                actor_user_id=actor_user_id,
                context=context,
                buffalo_id=buffalo.id,
                metadata={"buffalo_id": buffalo.id, "status": buffalo.status},
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                f"Buffalo with tag number '{normalized_tag}' already exists",
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(buffalo)
        return serialize_buffalo(buffalo)

    async def update_buffalo(
        self,
        raw_id: str,
        payload: UpdateBuffaloRequest,
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        buffalo_id = parse_buffalo_id(raw_id)
        buffalo = await self.repository.get_by_id(buffalo_id)
        if buffalo is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Buffalo with id {raw_id} not found",
            )

        updates = payload.model_dump(exclude_unset=True)
        new_tag: str | None = None
        changed_fields: list[str] = []
        previous_status = buffalo.status

        if "tag_no" in updates:
            normalized_tag = updates["tag_no"].strip().upper()
            if normalized_tag != buffalo.tag_no:
                existing = await self.repository.get_by_tag_no(
                    normalized_tag,
                    exclude_id=buffalo.id,
                )
                if existing is not None:
                    raise api_error(
                        status.HTTP_409_CONFLICT,
                        "DUPLICATE_ENTRY",
                        f"Tag number '{normalized_tag}' is already assigned "
                        "to another buffalo",
                    )
                buffalo.tag_no = normalized_tag
                new_tag = normalized_tag
                changed_fields.append("tag_no")

        if "name" in updates:
            name = updates["name"].strip()
            if buffalo.name != name:
                buffalo.name = name
                changed_fields.append("name")
        if "breed" in updates:
            breed = updates["breed"].strip()
            if buffalo.breed != breed:
                buffalo.breed = breed
                changed_fields.append("breed")
        if "dob" in updates:
            dob = _date_value(updates["dob"])
            if buffalo.dob != dob:
                buffalo.dob = dob
                changed_fields.append("dob")
        if "purchase_date" in updates:
            purchase_date = _date_value(updates["purchase_date"])
            if buffalo.purchase_date != purchase_date:
                buffalo.purchase_date = purchase_date
                changed_fields.append("purchase_date")
        if "status" in updates:
            if buffalo.status != updates["status"]:
                buffalo.status = updates["status"]
                changed_fields.append("status")

        try:
            if changed_fields:
                if previous_status != buffalo.status:
                    await self._record(
                        event_type="buffalo.status.changed",
                        actor_user_id=actor_user_id,
                        context=context,
                        buffalo_id=buffalo.id,
                        metadata={
                            "buffalo_id": buffalo.id,
                            "from_status": previous_status,
                            "to_status": buffalo.status,
                        },
                    )
                other_fields = [
                    field for field in changed_fields if field != "status"
                ]
                if other_fields:
                    await self._record(
                        event_type="buffalo.updated",
                        actor_user_id=actor_user_id,
                        context=context,
                        buffalo_id=buffalo.id,
                        metadata={
                            "buffalo_id": buffalo.id,
                            "changed_fields": other_fields,
                        },
                    )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            message = (
                f"Tag number '{new_tag}' is already assigned to another buffalo"
                if new_tag is not None
                else "Duplicate entry conflict"
            )
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                message,
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(buffalo)
        return serialize_buffalo(buffalo)

    async def get_counts(self) -> dict[str, int]:
        counts = await self.repository.count_by_status()
        result = {"total": 0, "active": 0, "dry": 0, "sold": 0, "dead": 0}
        for status_name, count in counts:
            result["total"] += count
            if status_name in result:
                result[status_name] = count
        return result
