from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_delete_service, require_admin
from app.services.delete_service import DeleteService

router = APIRouter(
    tags=["delete"],
    dependencies=[Depends(require_admin)],
)


@router.delete("/{resource}/{id}")
async def soft_delete(
    resource: str,
    id: str,
    service: DeleteService = Depends(get_delete_service),
) -> dict[str, Any]:
    return await service.soft_delete_resource(resource, id)
