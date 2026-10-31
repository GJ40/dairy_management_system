from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.time import iso_timestamp

QUERY_CATEGORIES = ("billing", "order", "delivery", "account", "other")
QUERY_STATUSES = ("open", "in_progress", "answered", "closed")
MAX_SUBJECT_LENGTH = 200
MAX_MESSAGE_LENGTH = 5000


def _received_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return normalized


def parse_category(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    normalized = value.strip().lower()
    if normalized not in QUERY_CATEGORIES:
        raise ValueError(
            "category: Expected one of billing, order, delivery, account, other"
        )
    return normalized


class CreateCustomerQueryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: Any
    subject: Any
    message: Any

    @field_validator("category")
    @classmethod
    def _category(cls, value: Any) -> str:
        return parse_category(value)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: Any) -> str:
        return _text(value, field="subject", maximum=MAX_SUBJECT_LENGTH)

    @field_validator("message")
    @classmethod
    def _message(cls, value: Any) -> str:
        return _text(value, field="message", maximum=MAX_MESSAGE_LENGTH)


class AddCustomerQueryMessageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: Any

    @field_validator("message")
    @classmethod
    def _message(cls, value: Any) -> str:
        return _text(value, field="message", maximum=MAX_MESSAGE_LENGTH)


class StaffAddQueryMessageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: Any
    is_internal: Any = False

    @field_validator("message")
    @classmethod
    def _message(cls, value: Any) -> str:
        return _text(value, field="message", maximum=MAX_MESSAGE_LENGTH)

    @field_validator("is_internal")
    @classmethod
    def _is_internal(cls, value: Any) -> bool:
        if value is None:
            return False
        if not isinstance(value, bool):
            raise ValueError("is_internal: Expected a boolean")
        return value


class QueryStatusRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Any

    @field_validator("status")
    @classmethod
    def _status(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(
                "Invalid input: expected string, received "
                f"{_received_type(value)}"
            )
        normalized = value.strip().lower()
        if normalized not in QUERY_STATUSES:
            raise ValueError(
                "status: Expected one of open, in_progress, answered, closed"
            )
        return normalized


class QueryAssignRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    assigned_to: Any

    @field_validator("assigned_to")
    @classmethod
    def _assigned_to(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("assigned_to: Expected an integer or null")
        if value <= 0:
            raise ValueError("assigned_to: Must be a positive integer")
        return value


@dataclass(slots=True)
class CustomerQueryListQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None


@dataclass(slots=True)
class StaffQueryListQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    assigned_to: int | None = None
    customer_id: int | None = None
    category: str | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def serialize_customer_query(query: Any) -> dict[str, Any]:
    return {
        "id": query.id,
        "query_no": query.query_no,
        "category": query.category,
        "subject": query.subject,
        "status": query.status,
        "last_message_at": iso_timestamp(query.last_message_at),
        "created_at": iso_timestamp(query.created_at),
        "updated_at": iso_timestamp(query.updated_at),
    }


def _customer_payload(customer: Any) -> dict[str, Any] | None:
    if customer is None:
        return None
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address,
    }


def _assignee_payload(user: Any) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "role": user.role,
    }


def serialize_staff_query(
    query: Any,
    *,
    customer: Any,
    assignee: Any,
    account_email: str | None,
) -> dict[str, Any]:
    data = serialize_customer_query(query)
    data["customer"] = _customer_payload(customer)
    data["assigned_to"] = _assignee_payload(assignee)
    data["account_email"] = account_email
    return data


def serialize_customer_message(message: Any) -> dict[str, Any]:
    return {
        "id": message.id,
        "body": message.body,
        "sender_type": message.sender_type,
        "created_at": iso_timestamp(message.created_at),
    }


def serialize_staff_message(message: Any) -> dict[str, Any]:
    data = serialize_customer_message(message)
    data["is_internal"] = bool(message.is_internal)
    return data


def serialize_customer_query_detail(
    query: Any,
    messages: list[Any],
) -> dict[str, Any]:
    data = serialize_customer_query(query)
    data["messages"] = [serialize_customer_message(row) for row in messages]
    return data


def serialize_staff_query_detail(
    query: Any,
    *,
    customer: Any,
    assignee: Any,
    account_email: str | None,
    messages: list[Any],
) -> dict[str, Any]:
    data = serialize_staff_query(query, customer=customer, assignee=assignee, account_email=account_email)
    data["messages"] = [serialize_staff_message(row) for row in messages]
    return data


def serialize_query_message(message: Any) -> dict[str, Any]:
    return serialize_customer_message(message)


__all__ = [
    "AddCustomerQueryMessageRequest",
    "CreateCustomerQueryRequest",
    "CustomerQueryListQuery",
    "QUERY_CATEGORIES",
    "QUERY_STATUSES",
    "QueryAssignRequest",
    "QueryStatusRequest",
    "StaffAddQueryMessageRequest",
    "StaffQueryListQuery",
    "serialize_customer_query",
    "serialize_customer_query_detail",
    "serialize_query_message",
    "serialize_staff_query",
    "serialize_staff_query_detail",
]
