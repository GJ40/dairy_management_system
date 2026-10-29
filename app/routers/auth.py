from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.user import LoginRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    return await service.login(payload.email, payload.password)


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    return {"user": await service.get_me(current_user.id)}
