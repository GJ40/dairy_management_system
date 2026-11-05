from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models.security_audit_event import SecurityAuditEvent

ActorLabels = Mapping[tuple[str, int], tuple[str | None, str | None]]


@dataclass(slots=True)
class SecurityAuditQuery:
    page: int = 1
    page_size: int = 20
    event_type: str | None = None
    category: str | None = None
    search: str | None = None
    actor_type: str | None = None
    actor_user_id: int | None = None
    actor_account_id: int | None = None
    severity: str | None = None
    outcome: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    from_created_at: datetime | None = None
    to_created_at: datetime | None = None


def _utc_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _actor_identity(
    event: SecurityAuditEvent,
    actor_labels: ActorLabels | None,
) -> tuple[str | None, str | None]:
    if not actor_labels:
        return None, None
    if event.actor_type == "staff" and event.actor_user_id is not None:
        return actor_labels.get(("staff", event.actor_user_id), (None, None))
    if event.actor_type == "customer" and event.actor_account_id is not None:
        return actor_labels.get(("customer", event.actor_account_id), (None, None))
    return None, None


def serialize_audit_event(
    event: SecurityAuditEvent,
    actor_labels: ActorLabels | None = None,
) -> dict[str, Any]:
    """Return only fields approved for the admin audit viewer.

    Metadata is already allowlisted and redacted on write. This serializer
    deliberately does not expose request bodies, credentials or internal
    storage details. ``actor_name``/``actor_email`` are resolved by the caller
    so an operator can identify who acted without cross-referencing raw ids.
    """
    actor_name, actor_email = _actor_identity(event, actor_labels)
    return {
        "id": event.id,
        "created_at": _utc_timestamp(event.created_at),
        "event_type": event.event_type,
        "category": event.event_type.split(".", 1)[0],
        "action": event.path or event.event_type,
        "outcome": event.outcome,
        "severity": event.severity,
        "actor_type": event.actor_type,
        "actor_user_id": event.actor_user_id,
        "actor_account_id": event.actor_account_id,
        "actor_name": actor_name,
        "actor_email": actor_email,
        "target_type": event.resource_type,
        "target_id": event.resource_id,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "request_id": event.request_id,
        "http_method": event.http_method,
        "path": event.path,
        "reason_code": event.reason_code,
        "metadata": event.event_metadata or {},
    }
