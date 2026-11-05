from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_security_audit_service, require_admin
from app.schemas.security_audit import SecurityAuditQuery
from app.services.security_audit_service import SecurityAuditService

router = APIRouter(
    prefix="/security-audit",
    tags=["security-audit"],
    dependencies=[Depends(require_admin)],
)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("")
async def list_security_audit_events(
    event_type: str | None = Query(default=None, max_length=64),
    category: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=100),
    actor_type: Literal["staff", "customer", "system", "anonymous"] | None = None,
    actor_user_id: int | None = Query(default=None, ge=1),
    actor_account_id: int | None = Query(default=None, ge=1),
    severity: Literal["info", "warning", "critical"] | None = None,
    outcome: Literal["success", "failure", "denied"] | None = None,
    target_type: str | None = Query(default=None, max_length=40),
    target_id: str | None = Query(default=None, max_length=64),
    request_id: str | None = Query(default=None, max_length=64),
    ip_address: str | None = Query(default=None, max_length=45),
    from_created_at: datetime | None = Query(default=None, alias="from"),
    to_created_at: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: SecurityAuditService = Depends(get_security_audit_service),
) -> dict[str, Any]:
    return await service.list_events(
        SecurityAuditQuery(
            page=page,
            page_size=page_size,
            event_type=event_type or None,
            category=category or None,
            search=search or None,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            severity=severity,
            outcome=outcome,
            target_type=target_type or None,
            target_id=target_id or None,
            request_id=request_id or None,
            ip_address=ip_address or None,
            from_created_at=_utc_naive(from_created_at),
            to_created_at=_utc_naive(to_created_at),
        )
    )


@router.get("/{event_id}")
async def get_security_audit_event(
    event_id: int,
    service: SecurityAuditService = Depends(get_security_audit_service),
) -> dict[str, Any]:
    return await service.get_event(event_id)
