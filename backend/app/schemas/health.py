from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    environment: str
    uptime_seconds: int
    timezone: str
    timestamp: str
    database: Literal["connected", "disconnected"]
