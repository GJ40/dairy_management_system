from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_delete_service, require_admin
from app.core.request_context import get_request_context
from app.models.user import User
from app.services.delete_service import DeleteService

router = APIRouter(
    tags=["delete"],
    dependencies=[Depends(require_admin)],
)


@router.delete("/{resource}/{id}")
async def soft_delete(
    resource: str,
    id: str,
    request: Request,
    user: User = Depends(require_admin),
    service: DeleteService = Depends(get_delete_service),
) -> dict[str, Any]:
    return await service.soft_delete_resource(
        resource,
        id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )
