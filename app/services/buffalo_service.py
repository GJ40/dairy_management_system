from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.core.errors import api_error
from app.repositories.buffalo_repository import BuffaloRepository
from app.schemas.buffalo import (
    BuffaloQuery,
    CreateBuffaloRequest,
    UpdateBuffaloRequest,
    serialize_buffalo,
)


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
    def __init__(self, repository: BuffaloRepository) -> None:
        self.repository = repository

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

    async def create_buffalo(self, payload: CreateBuffaloRequest) -> dict[str, Any]:
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
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                f"Buffalo with tag number '{normalized_tag}' already exists",
            ) from exc
        await self.repository.refresh(buffalo)
        return serialize_buffalo(buffalo)

    async def update_buffalo(
        self,
        raw_id: str,
        payload: UpdateBuffaloRequest,
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

        if "name" in updates:
            buffalo.name = updates["name"].strip()
        if "breed" in updates:
            buffalo.breed = updates["breed"].strip()
        if "dob" in updates:
            buffalo.dob = _date_value(updates["dob"])
        if "purchase_date" in updates:
            buffalo.purchase_date = _date_value(updates["purchase_date"])
        if "status" in updates:
            buffalo.status = updates["status"]

        try:
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
