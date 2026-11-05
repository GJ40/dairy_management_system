from __future__ import annotations

import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.audit_events import ActorType, get_event_definition
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.security_audit_event import SecurityAuditEvent
from app.repositories.security_audit_repository import SecurityAuditRepository
from app.schemas.security_audit import SecurityAuditQuery, serialize_audit_event
from app.utils.time import utc_now_naive

logger = logging.getLogger("app.security.audit")

MAX_METADATA_KEYS = 20
MAX_METADATA_ITEMS = 20
MAX_METADATA_DEPTH = 2
MAX_KEY_LENGTH = 64
MAX_STRING_LENGTH = 256

FORBIDDEN_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "hash",
    "otp",
    "api_key",
    "apikey",
    "credential",
)


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in FORBIDDEN_KEY_MARKERS)


def _sanitize_string(value: str) -> str:
    cleaned = "".join(
        character if character.isprintable() else " " for character in value
    )
    return cleaned[:MAX_STRING_LENGTH]


def _sanitize_value(value: object, *, depth: int) -> object:
    if depth > MAX_METADATA_DEPTH:
        raise ValueError("Security audit metadata is nested too deeply")

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Security audit metadata contains a non-finite number")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_METADATA_ITEMS:
            raise ValueError("Security audit metadata list is too long")
        return [_sanitize_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError("Security audit metadata object has too many keys")
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Security audit metadata keys must be non-empty text")
            if len(key) > MAX_KEY_LENGTH or _is_forbidden_key(key):
                raise ValueError("Security audit metadata contains a forbidden key")
            cleaned[key] = _sanitize_value(item, depth=depth + 1)
        return cleaned

    raise ValueError(
        f"Unsupported security audit metadata value: {type(value).__name__}"
    )


def sanitize_metadata(
    metadata: dict[str, object] | None,
    *,
    allowed_keys: frozenset[str],
) -> dict[str, Any] | None:
    """Validate metadata against an event allowlist and redact it.

    Unknown keys are rejected rather than dropped so a programming mistake
    cannot silently put a new field into the security ledger.
    """
    if not metadata:
        return None
    if not isinstance(metadata, dict):
        raise ValueError("Security audit metadata must be an object")
    if len(metadata) > MAX_METADATA_KEYS:
        raise ValueError("Security audit metadata has too many keys")

    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Security audit metadata keys must be non-empty text")
        if key not in allowed_keys:
            raise ValueError(f"Metadata key is not allowed for this event: {key}")
        if len(key) > MAX_KEY_LENGTH or _is_forbidden_key(key):
            raise ValueError(f"Forbidden security audit metadata key: {key}")
        cleaned[key] = _sanitize_value(value, depth=1)
    return cleaned


def _optional_text(value: object, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _sanitize_string(text)[:max_length]


def _resolve_actor_type(
    *,
    actor_user_id: int | None,
    actor_account_id: int | None,
    actor_type: str | None,
) -> ActorType:
    if actor_user_id is not None and actor_account_id is not None:
        raise ValueError("A security audit event cannot have two actor identities")

    if actor_type is not None:
        normalized = actor_type.strip().lower()
        if normalized not in {"staff", "customer", "system", "anonymous"}:
            raise ValueError(f"Unknown security audit actor type: {actor_type}")
        if normalized == "staff" and actor_user_id is None:
            raise ValueError("Staff audit events require actor_user_id")
        if normalized == "customer" and actor_account_id is None:
            raise ValueError("Customer audit events require actor_account_id")
        if normalized in {"system", "anonymous"} and (
            actor_user_id is not None or actor_account_id is not None
        ):
            raise ValueError(f"{normalized} audit events cannot have an actor identity")
        return normalized  # type: ignore[return-value]

    if actor_user_id is not None:
        return "staff"
    if actor_account_id is not None:
        return "customer"
    return "anonymous"


class SecurityAuditService:
    def __init__(
        self,
        repository: SecurityAuditRepository,
        *,
        standalone_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.repository = repository
        self.standalone_session_factory = standalone_session_factory

    async def record(
        self,
        *,
        event_type: str,
        context: RequestContext | None = None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        actor_type: str | None = None,
        resource_type: str | None = None,
        resource_id: object | None = None,
        reason_code: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SecurityAuditEvent:
        definition = get_event_definition(event_type)
        resolved_actor_type = _resolve_actor_type(
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            actor_type=actor_type,
        )
        if resolved_actor_type not in definition.actor_types:
            raise ValueError(
                f"Actor type {resolved_actor_type} is not allowed for {event_type}"
            )

        cleaned_metadata = sanitize_metadata(
            metadata,
            allowed_keys=definition.allowed_metadata,
        )
        event = SecurityAuditEvent(
            created_at=utc_now_naive(),
            event_type=event_type,
            outcome=definition.outcome,
            severity=definition.severity,
            actor_type=resolved_actor_type,
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            ip_address=context.ip_address if context is not None else None,
            user_agent=context.user_agent if context is not None else None,
            request_id=context.request_id if context is not None else None,
            http_method=context.http_method if context is not None else None,
            path=context.path if context is not None else None,
            resource_type=_optional_text(resource_type, max_length=40),
            resource_id=_optional_text(resource_id, max_length=64),
            reason_code=_optional_text(reason_code, max_length=64),
            event_metadata=cleaned_metadata,
        )
        self.repository.add(event)
        return event

    async def record_standalone(
        self,
        *,
        event_type: str,
        context: RequestContext | None = None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        actor_type: str | None = None,
        resource_type: str | None = None,
        resource_id: object | None = None,
        reason_code: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        """Best-effort write that never changes the caller's response.

        This is for auth failures and denials, where there is no privileged
        business transaction to join. Privileged mutations must call `record`
        in the same transaction and let a failure abort the mutation.
        """
        try:
            if self.standalone_session_factory is not None:
                async with self.standalone_session_factory() as session:
                    service = SecurityAuditService(
                        SecurityAuditRepository(session)
                    )
                    await service.record(
                        event_type=event_type,
                        context=context,
                        actor_user_id=actor_user_id,
                        actor_account_id=actor_account_id,
                        actor_type=actor_type,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        reason_code=reason_code,
                        metadata=metadata,
                    )
                    await session.commit()
            else:
                await self.record(
                    event_type=event_type,
                    context=context,
                    actor_user_id=actor_user_id,
                    actor_account_id=actor_account_id,
                    actor_type=actor_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    reason_code=reason_code,
                    metadata=metadata,
                )
                await self.repository.commit()
        except Exception:
            logger.exception(
                "Security audit write failed (event_type=%s)",
                event_type,
            )
            if self.standalone_session_factory is None:
                try:
                    await self.repository.rollback()
                except Exception:
                    logger.exception("Security audit rollback failed")
            return False
        return True

    async def list_events(self, query: SecurityAuditQuery) -> dict[str, Any]:
        if (
            query.from_created_at is not None
            and query.to_created_at is not None
            and query.from_created_at > query.to_created_at
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "from: Must be before or equal to to",
            )
        rows, total = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            event_type=query.event_type,
            category=query.category,
            search=query.search,
            ip_address=query.ip_address,
            outcome=query.outcome,
            severity=query.severity,
            actor_type=query.actor_type,
            actor_user_id=query.actor_user_id,
            actor_account_id=query.actor_account_id,
            request_id=query.request_id,
            resource_type=query.target_type,
            resource_id=query.target_id,
            from_created_at=query.from_created_at,
            to_created_at=query.to_created_at,
        )
        actor_labels = await self.repository.resolve_actor_labels(rows)
        return {
            "items": [
                serialize_audit_event(row, actor_labels) for row in rows
            ],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def get_event(self, event_id: int) -> dict[str, Any]:
        event = await self.repository.get_by_id(event_id)
        if event is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Audit event with id {event_id} not found",
            )
        actor_labels = await self.repository.resolve_actor_labels([event])
        return {"event": serialize_audit_event(event, actor_labels)}

    async def count_recent(
        self,
        *,
        event_type: str,
        since: datetime,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> int:
        """Count recent events without changing the caller's response.

        Alerting runs after the response, so a count failure must degrade to
        "no alert" rather than surface as an error.
        """
        try:
            if self.standalone_session_factory is not None:
                async with self.standalone_session_factory() as session:
                    return await SecurityAuditRepository(session).count_recent(
                        event_type=event_type,
                        since=since,
                        actor_user_id=actor_user_id,
                        actor_account_id=actor_account_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
            return await self.repository.count_recent(
                event_type=event_type,
                since=since,
                actor_user_id=actor_user_id,
                actor_account_id=actor_account_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except Exception:
            logger.exception(
                "Security audit count failed (event_type=%s)",
                event_type,
            )
            return 0
