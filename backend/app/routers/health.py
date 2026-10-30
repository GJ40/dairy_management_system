from __future__ import annotations

import time

from fastapi import APIRouter

from app.core.config import settings
from app.db import session as db_session
from app.schemas.health import HealthResponse
from app.utils.time import utc_now_iso

router = APIRouter(tags=["Health"])

_PROCESS_STARTED = time.monotonic()


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    connected = await db_session.check_database()
    return HealthResponse(
        status="ok",
        environment=settings.node_env,
        uptime_seconds=int(time.monotonic() - _PROCESS_STARTED),
        timezone=settings.tz,
        timestamp=utc_now_iso(),
        database="connected" if connected else "disconnected",
    )
