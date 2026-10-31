from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def _original_url(request: Request) -> str:
    query = request.url.query
    if query:
        return f"{request.url.path}?{query}"
    return request.url.path


def _status_code_to_error_code(status_code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "DUPLICATE_ENTRY",
        status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    }.get(status_code, "INTERNAL_ERROR")


STRING_FIELDS = {
    "full_name",
    "username",
    "email",
    "password",
    "tag_no",
    "name",
    "breed",
    "dob",
    "purchase_date",
    "prod_date",
    "waste_date",
    "sale_date",
    "period_start",
    "period_end",
    "expense_date",
    "note",
    "phone",
    "address",
    "from",
    "to",
    "date",
}
NUMBER_FIELDS = {
    "buffalo_id",
    "customer_id",
    "category_id",
    "rate",
    "rate_per_litre",
    "amount",
    "litres",
    "morning_litres",
    "evening_litres",
    "page",
    "page_size",
}
BOOLEAN_FIELDS = {"is_active", "overwrite"}
ARRAY_FIELDS = {"entries"}
ENUM_FIELDS = {
    "role": '"admin"|"operator"',
    "status": '"active"|"sold"|"dry"|"dead"',
    "session": '"morning"|"evening"',
    "reason": '"spoiled"|"spilled"|"returned"',
    "payment_status": '"unpaid"|"paid"',
}
FIELD_LABELS = {
    "full_name": "Full name",
    "username": "Username",
    "email": "Email",
    "password": "Password",
    "role": "Role",
    "is_active": "is_active",
    "tag_no": "Tag number",
    "name": "Name",
    "breed": "Breed",
    "dob": "Date of birth",
    "purchase_date": "Purchase date",
    "status": "Status",
    "category": "Category",
    "category_id": "Category ID",
    "expense_date": "Expense date",
    "recorded_by": "Recorded by",
    "note": "Note",
}


def _missing_message(field: str) -> str:
    name = field.rsplit(".", 1)[-1]
    if name in ENUM_FIELDS:
        return f"Invalid option: expected one of {ENUM_FIELDS[name]}"
    if name in NUMBER_FIELDS:
        return "Invalid input: expected number, received NaN"
    if name in BOOLEAN_FIELDS:
        return "Invalid input: expected boolean, received undefined"
    if name in ARRAY_FIELDS:
        return "Invalid input: expected array, received undefined"
    if name in STRING_FIELDS:
        return "Invalid input: expected string, received undefined"
    return f"{FIELD_LABELS.get(field, field.replace('_', ' ').capitalize())} is required"


def _received_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _validation_error_message(errors: list[dict[str, Any]]) -> tuple[str, str]:
    if any(error.get("type") == "json_invalid" for error in errors):
        return "INVALID_JSON", "Invalid JSON payload received"

    first = errors[0] if errors else {}
    location = [
        part
        for part in first.get("loc", ())
        if part not in ("body", "query", "path", "header", "cookie")
    ]
    error_type = str(first.get("type") or "")
    if not location:
        if error_type in ("model_type", "model_attributes_type", "dict_type"):
            return (
                "VALIDATION_ERROR",
                "field: Invalid input: expected object, received "
                f"{_received_type(first.get('input'))}",
            )
        return "VALIDATION_ERROR", "body: Expected object, received undefined"

    field = ".".join(str(part) for part in location)
    message = str(first.get("msg") or "Validation failed")
    if message.startswith("Value error, "):
        message = message[len("Value error, ") :]

    if error_type == "missing":
        message = _missing_message(field)
    elif error_type in ("string_type", "string_unicode"):
        message = (
            f"Invalid input: expected string, received {_received_type(first.get('input'))}"
        )
    elif error_type in ("bool_type", "bool_parsing"):
        message = (
            f"Invalid input: expected boolean, received {_received_type(first.get('input'))}"
        )
    elif error_type == "list_type":
        message = (
            f"Invalid input: expected array, received {_received_type(first.get('input'))}"
        )
    elif error_type in ("int_parsing", "float_parsing"):
        message = "Invalid input: expected number, received NaN"
    elif error_type == "int_from_float":
        message = "Invalid input: expected int, received number"
    elif error_type in ("string_too_short", "string_too_long"):
        context = first.get("ctx") or {}
        if error_type == "string_too_short":
            message = (
                "Too small: expected string to have "
                f">={context.get('min_length')} characters"
            )
        else:
            message = (
                "Too big: expected string to have "
                f"<={context.get('max_length')} characters"
            )
    elif error_type == "greater_than_equal":
        message = (
            "Too small: expected number to be "
            f">={first.get('ctx', {}).get('ge')}"
        )
    elif error_type == "less_than_equal":
        message = (
            "Too big: expected number to be "
            f"<={first.get('ctx', {}).get('le')}"
        )

    return "VALIDATION_ERROR", f"{field}: {message}"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        code, message = _validation_error_message(exc.errors())
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_payload(code, message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if exc.status_code in (
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ) and not isinstance(exc.detail, dict):
            message = f"Cannot {request.method} {_original_url(request)}"
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=_payload("NOT_FOUND", message),
            )

        detail = exc.detail
        if isinstance(detail, dict):
            code = str(detail.get("code") or _status_code_to_error_code(exc.status_code))
            message = str(detail.get("message") or detail.get("detail") or detail)
        else:
            code = _status_code_to_error_code(exc.status_code)
            message = str(detail)

        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error while handling %s %s",
            request.method,
            request.url.path,
        )
        message = "Internal server error" if settings.is_production else (
            str(exc) or "An unexpected error occurred"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("INTERNAL_ERROR", message),
        )
