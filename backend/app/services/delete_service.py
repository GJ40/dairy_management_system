from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.buffalo import Buffalo
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.milk_production import MilkProduction
from app.models.milk_wastage import MilkWastage
from app.models.sale import Sale
from app.repositories.delete_repository import DeleteRepository
from app.utils.time import utc_now_iso

RESOURCE_MODEL_MAP = {
    "buffaloes": Buffalo,
    "customers": Customer,
    "sales": Sale,
    "invoices": Invoice,
    "expenses": Expense,
    "production": MilkProduction,
    "wastage": MilkWastage,
}
ALLOWED_RESOURCES = list(RESOURCE_MODEL_MAP)


def parse_record_id(raw_id: str) -> int | None:
    if not raw_id.isdigit():
        return None
    return int(raw_id)


class DeleteService:
    def __init__(self, repository: DeleteRepository) -> None:
        self.repository = repository

    async def soft_delete_resource(self, resource: str, raw_id: str) -> dict[str, Any]:
        normalized_resource = str(resource).strip().lower()
        model = RESOURCE_MODEL_MAP.get(normalized_resource)
        if model is None:
            allowed = ", ".join(ALLOWED_RESOURCES)
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "UNSUPPORTED_RESOURCE",
                f"Unsupported resource '{resource}' for deletion. "
                f"Allowed resources: [{allowed}]",
            )

        record_id = parse_record_id(raw_id)
        record = (
            None
            if record_id is None
            else await self.repository.soft_delete(model, record_id)
        )
        if record is None:
            singular = normalized_resource[:-1]
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"{singular} with id {raw_id} not found or has already been deleted",
            )

        return {
            "message": f"{normalized_resource} record #{raw_id} soft-deleted successfully",
            "resource": normalized_resource,
            "id": record.id,
            "deleted_at": utc_now_iso(),
        }
