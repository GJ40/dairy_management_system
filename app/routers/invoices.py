from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_invoice_service, require_roles
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.invoice import (
    DATE_PATTERN,
    CreateInvoiceRequest,
    InvoiceQuery,
    RecordPaymentRequest,
)
from app.services.invoice_service import InvoiceService

router = APIRouter(
    prefix="/invoices",
    tags=["invoices"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


def _validation_error(message: str) -> NoReturn:
    raise api_error(
        status.HTTP_400_BAD_REQUEST,
        "VALIDATION_ERROR",
        message,
    )


def _parse_int_param(
    raw: str | None,
    *,
    name: str,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if raw is None:
        return default
    text = raw.strip()
    try:
        number = 0.0 if text == "" else float(text)
    except ValueError:
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if math.isnan(number) or math.isinf(number):
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if not number.is_integer():
        _validation_error(f"{name}: Invalid input: expected int, received number")
    value = int(number)
    if value < minimum:
        _validation_error(f"{name}: Too small: expected number to be >={minimum}")
    if maximum is not None and value > maximum:
        _validation_error(f"{name}: Too big: expected number to be <={maximum}")
    return value


def _optional_positive_int(params: Any, name: str) -> int | None:
    raw = params.get(name)
    if raw is None:
        return None
    text = raw.strip()
    try:
        number = 0.0 if text == "" else float(text)
    except ValueError:
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if math.isnan(number) or math.isinf(number):
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if not number.is_integer():
        _validation_error(f"{name}: Invalid input: expected int, received number")
    value = int(number)
    if value <= 0:
        _validation_error(f"{name}: Too small: expected number to be >0")
    return value


def _optional_date(params: Any, name: str) -> str | None:
    value = params.get(name)
    if value is not None and not DATE_PATTERN.match(value):
        _validation_error(
            f"{name}: {name} must be in 'YYYY-MM-DD' format"
        )
    return value


def parse_invoice_query(request: Request) -> InvoiceQuery:
    params = request.query_params
    page = _parse_int_param(
        params.get("page"),
        name="page",
        default=1,
        minimum=1,
    )
    page_size = _parse_int_param(
        params.get("page_size"),
        name="page_size",
        default=20,
        minimum=1,
        maximum=100,
    )
    customer_id = _optional_positive_int(params, "customer_id")

    invoice_status = params.get("status")
    if invoice_status is not None and invoice_status not in (
        "unpaid",
        "partial",
        "paid",
    ):
        _validation_error(
            'status: Invalid option: expected one of "unpaid"|"partial"|"paid"'
        )

    return InvoiceQuery(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=invoice_status,
        from_date=_optional_date(params, "from"),
        to_date=_optional_date(params, "to"),
    )


@router.get("")
async def list_invoices(
    query: InvoiceQuery = Depends(parse_invoice_query),
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, Any]:
    return await service.list_invoices(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, Any]:
    try:
        payload = CreateInvoiceRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return {
        "invoice": await service.create_invoice(
            payload,
            actor_user_id=user.id,
            context=get_request_context(request),
        )
    }


@router.get("/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: str,
    request: Request,
    user: User = Depends(require_roles("admin", "operator")),
    service: InvoiceService = Depends(get_invoice_service),
) -> Response:
    content, filename = await service.generate_invoice_pdf(
        invoice_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, Any]:
    return {"invoice": await service.get_invoice_by_id(invoice_id)}


@router.patch("/{invoice_id}/payment")
async def record_payment(
    invoice_id: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, Any]:
    try:
        payload = RecordPaymentRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return {
        "invoice": await service.record_payment(
            invoice_id,
            payload,
            actor_user_id=user.id,
            context=get_request_context(request),
        )
    }
