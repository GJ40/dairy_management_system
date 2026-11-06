from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from fastapi import BackgroundTasks, status

from app.core.config import settings
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.user import User
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_query_repository import CustomerQueryRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.user_repository import UserRepository
from app.schemas.customer_queries import (
    QUERY_STATUSES,
    CustomerQueryListQuery,
    StaffQueryListQuery,
    serialize_customer_query,
    serialize_customer_query_detail,
    serialize_query_message,
    serialize_staff_message,
    serialize_staff_query,
    serialize_staff_query_detail,
)
from app.services.email_service import EmailService
from app.services.security_audit_service import SecurityAuditService
from app.utils.tasks import deliver_or_queue
from app.utils.time import business_now, business_now_naive, utc_now_naive

logger = logging.getLogger(__name__)

# Internal-observer workflow events for the support-query workflow.
SUPPORT_QUERY_RECEIVED_EVENT = "support.query_received"
SUPPORT_QUERY_ANSWERED_EVENT = "support.query_answered"

InternalDispatch = Callable[[str, dict[str, Any] | None], Awaitable[int]]

OPERATOR_TRANSITIONS = {
    ("open", "in_progress"),
    ("in_progress", "open"),
    ("in_progress", "answered"),
    ("answered", "answered"),
}
ADMIN_TRANSITIONS = OPERATOR_TRANSITIONS | {
    ("open", "closed"),
    ("in_progress", "closed"),
    ("answered", "closed"),
    ("closed", "open"),
}
CUSTOMER_MESSAGEABLE = ("open", "in_progress", "answered")


class CustomerQueryService:
    def __init__(
        self,
        repository: CustomerQueryRepository,
        customer_repository: CustomerRepository,
        account_repository: CustomerPortalAccountRepository,
        user_repository: UserRepository,
        audit: SecurityAuditService | None = None,
        *,
        email_service: EmailService | None = None,
        internal_dispatch: InternalDispatch | None = None,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        self.account_repository = account_repository
        self.user_repository = user_repository
        self.audit = audit
        # Both are optional so every existing caller (and test) keeps working:
        # with no notifier configured, a query transition simply sends nothing.
        self.email_service = email_service
        self.internal_dispatch = internal_dispatch

    async def create(
        self,
        account: CustomerPortalAccount,
        *,
        category: str,
        subject: str,
        message: str,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "CUSTOMER_INACTIVE",
                "The linked customer account is inactive",
            )

        now = business_now_naive()
        query = await self.repository.create(
            query_no=await self._generate_query_number(business_now().date()),
            customer_id=customer.id,
            account_id=account.id,
            category=category,
            subject=subject,
            last_message_at=now,
        )
        await self.repository.add_message(
            query_id=query.id,
            body=message,
            sender_type="customer",
            sender_account_id=account.id,
        )
        if self.audit is not None:
            await self.audit.record(
                event_type="query.created",
                context=context,
                actor_account_id=account.id,
                resource_type="customer_query",
                resource_id=query.id,
                metadata={
                    "query_id": query.id,
                    "query_no": query.query_no,
                    "category": query.category,
                },
            )
        await self._commit(query)
        # Internal observers only: the customer already sees the query in the
        # portal, so a receipt email would add noise without information.
        await self._notify_internal(
            SUPPORT_QUERY_RECEIVED_EVENT,
            {
                "occurred_at": utc_now_naive().isoformat(),
                "account_email": account.email,
                "account_name": getattr(customer, "name", None),
                "query_no": query.query_no,
                "query_subject": query.subject,
                "query_category": query.category,
            },
            background=background,
        )
        return {"query": await self._customer_detail(query)}

    async def list_queries(
        self,
        account: CustomerPortalAccount,
        query: CustomerQueryListQuery,
    ) -> dict[str, Any]:
        if query.status is not None and query.status not in QUERY_STATUSES:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "status: Invalid query status",
            )
        rows, total = await self.repository.list_own_and_count(
            customer_id=account.customer_id,
            page=query.page,
            page_size=query.page_size,
            status=query.status,
        )
        return _page_payload(rows, total, query.page, query.page_size)

    async def get_query(
        self,
        account: CustomerPortalAccount,
        query_id: int,
    ) -> dict[str, Any]:
        query = await self._get_owned(account, query_id)
        return {"query": await self._customer_detail(query)}

    async def add_customer_message(
        self,
        account: CustomerPortalAccount,
        query_id: int,
        body: str,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        query = await self._get_owned(account, query_id)
        if query.status == "closed":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "QUERY_CLOSED",
                "This query is closed and cannot receive new messages",
            )

        message = await self.repository.add_message(
            query_id=query.id,
            body=body,
            sender_type="customer",
            sender_account_id=account.id,
        )
        if query.status == "answered":
            query.status = "open"
            await self._record_status_change(query, "answered", "open")
        query.last_message_at = message.created_at or business_now_naive()
        if self.audit is not None:
            await self.audit.record(
                event_type="query.customer_message",
                context=context,
                actor_account_id=account.id,
                resource_type="customer_query",
                resource_id=query.id,
                metadata={"query_id": query.id, "message_id": message.id},
            )
        await self._commit(query)
        return {"message": serialize_query_message(message)}

    async def staff_list_queries(
        self,
        query: StaffQueryListQuery,
    ) -> dict[str, Any]:
        if query.status is not None and query.status not in QUERY_STATUSES:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "status: Invalid query status",
            )
        rows, total = await self.repository.list_all_and_count(
            page=query.page,
            page_size=query.page_size,
            status=query.status,
            assigned_to=query.assigned_to,
            customer_id=query.customer_id,
            category=query.category,
        )
        items = []
        for row in rows:
            customer = await self.customer_repository.get_by_id(row.customer_id)
            assignee = (
                await self.user_repository.get_by_id(row.assigned_to)
                if row.assigned_to is not None
                else None
            )
            account = await self.account_repository.get_by_id(row.account_id)
            items.append(
                serialize_staff_query(
                    row,
                    customer=customer,
                    assignee=assignee,
                    account_email=account.email if account is not None else None,
                )
            )
        return {
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def staff_get_query(self, query_id: int) -> dict[str, Any]:
        query = await self._get_any(query_id)
        return {"query": await self._staff_detail(query)}

    async def add_staff_message(
        self,
        user: User,
        query_id: int,
        body: str,
        *,
        is_internal: bool,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        query = await self._get_any(query_id)
        await self._require_assignment(
            user,
            query,
            "internal_note" if is_internal else "message",
            context,
        )
        if query.status == "closed":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "QUERY_CLOSED",
                "This query is closed and cannot receive new messages",
            )
        message = await self.repository.add_message(
            query_id=query.id,
            body=body,
            sender_type="staff",
            sender_user_id=user.id,
            is_internal=is_internal,
        )
        query.last_message_at = message.created_at or business_now_naive()
        if self.audit is not None:
            await self.audit.record(
                event_type=(
                    "query.internal_note" if is_internal else "query.staff_message"
                ),
                context=context,
                actor_user_id=user.id,
                resource_type="customer_query",
                resource_id=query.id,
                metadata={
                    "query_id": query.id,
                    "message_id": message.id,
                    "is_internal": is_internal,
                },
            )
        await self._commit(query)

        # A visible reply is the moment the customer gains new information, so
        # that is what triggers the mail - not the status control, which staff
        # may use alone or after replying. Skipping an already-answered query
        # keeps a follow-up on a settled thread from mailing twice.
        if not is_internal and query.status != "answered":
            await self._send_reply_email(query, background=background)

        return {"message": serialize_staff_message(message)}

    async def change_status(
        self,
        user: User,
        query_id: int,
        target: str,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        query = await self._get_any(query_id)
        await self._require_assignment(user, query, "status_change", context)
        current = query.status
        allowed = (
            ADMIN_TRANSITIONS if user.role == "admin" else OPERATOR_TRANSITIONS
        )
        if target != current and (current, target) not in allowed:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "INVALID_QUERY_TRANSITION",
                f"Cannot move query from '{current}' to '{target}'",
            )

        if target != current:
            query.status = target
            await self._record_status_change(query, current, target)
            if self.audit is not None:
                await self.audit.record(
                    event_type="query.status.changed",
                    context=context,
                    actor_user_id=user.id,
                    resource_type="customer_query",
                    resource_id=query.id,
                    metadata={
                        "query_id": query.id,
                        "from_status": current,
                        "to_status": target,
                    },
                )
            await self._commit(query)
        return {"query": await self._staff_detail(query)}

    async def assign(
        self,
        user: User,
        query_id: int,
        assigned_to: int | None,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        query = await self._get_any(query_id)
        previous_assignee = query.assigned_to
        assignee = None
        if assigned_to is not None:
            assignee = await self.user_repository.get_by_id(assigned_to)
            if (
                assignee is None
                or assignee.is_deleted
                or not assignee.is_active
                or assignee.role not in ("admin", "operator")
            ):
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "assigned_to: Must reference an active staff user",
                )

        query.assigned_to = assigned_to
        if self.audit is not None and previous_assignee != assigned_to:
            await self.audit.record(
                event_type=(
                    "query.assigned" if assigned_to is not None else "query.unassigned"
                ),
                context=context,
                actor_user_id=user.id,
                resource_type="customer_query",
                resource_id=query.id,
                metadata=(
                    {
                        "query_id": query.id,
                        "from_user_id": previous_assignee,
                        "to_user_id": assigned_to,
                    }
                    if assigned_to is not None
                    else {
                        "query_id": query.id,
                        "from_user_id": previous_assignee,
                    }
                ),
            )
        message = await self.repository.add_message(
            query_id=query.id,
            body=(
                f"Assigned to {assignee.full_name}"
                if assignee is not None
                else "Unassigned"
            ),
            sender_type="system",
            is_internal=True,
        )
        query.last_message_at = message.created_at or business_now_naive()
        await self._commit(query)
        return {"query": await self._staff_detail(query)}

    async def _require_assignment(
        self,
        user: User,
        query: Any,
        attempted_action: str,
        context: RequestContext | None,
    ) -> None:
        if user.role == "admin" or query.assigned_to == user.id:
            return

        if self.audit is not None:
            await self.audit.record_standalone(
                event_type="query.access.denied",
                context=context,
                actor_user_id=user.id,
                resource_type="customer_query",
                resource_id=query.id,
                metadata={
                    "query_id": query.id,
                    "assigned_to_user_id": query.assigned_to,
                    "attempted_action": attempted_action,
                },
            )
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "QUERY_NOT_ASSIGNED",
            "This query is not assigned to you",
        )

    async def _notify_internal(
        self,
        event_key: str,
        payload: dict[str, Any],
        *,
        background: BackgroundTasks | None,
    ) -> None:
        """Best-effort internal copy; never changes the query flow."""
        if self.internal_dispatch is None:
            return
        try:
            await deliver_or_queue(
                background,
                self.internal_dispatch,
                event_key=event_key,
                payload=payload,
            )
        except Exception:
            logger.exception(
                "Internal notification dispatch for %r raised", event_key
            )

    async def _send_reply_email(
        self,
        query: Any,
        *,
        background: BackgroundTasks | None,
    ) -> None:
        """Tell the customer the reply is waiting in the portal."""
        if self.email_service is None:
            return

        account = await self.account_repository.get_by_id(query.account_id)
        email = ""
        if account is not None and account.is_active:
            email = (account.email or "").strip().lower()
        if not email:
            logger.info(
                "Query %s has no active portal address; %r not sent",
                query.query_no,
                SUPPORT_QUERY_ANSWERED_EVENT,
            )
            return

        customer = await self.customer_repository.get_by_id(query.customer_id)
        await deliver_or_queue(
            background,
            self.email_service.send_support_query_answered,
            to=email,
            name=getattr(customer, "name", None) or "there",
            query_no=query.query_no,
            subject=query.subject or "",
            portal_url=f"{settings.frontend_base_url}/portal/queries",
        )

    async def _record_status_change(
        self,
        query: Any,
        current: str,
        target: str,
    ) -> None:
        message = await self.repository.add_message(
            query_id=query.id,
            body=f"Status changed from '{current}' to '{target}'",
            sender_type="system",
        )
        query.last_message_at = message.created_at or business_now_naive()

    async def _customer_detail(self, query: Any) -> dict[str, Any]:
        messages = await self.repository.list_messages(
            query.id,
            include_internal=False,
        )
        return serialize_customer_query_detail(query, messages)

    async def _staff_detail(self, query: Any) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(query.customer_id)
        assignee = (
            await self.user_repository.get_by_id(query.assigned_to)
            if query.assigned_to is not None
            else None
        )
        account = await self.account_repository.get_by_id(query.account_id)
        messages = await self.repository.list_messages(
            query.id,
            include_internal=True,
        )
        return serialize_staff_query_detail(
            query,
            customer=customer,
            assignee=assignee,
            account_email=account.email if account is not None else None,
            messages=messages,
        )

    async def _get_owned(
        self,
        account: CustomerPortalAccount,
        query_id: int,
    ) -> Any:
        query = await self.repository.get_owned(query_id, account.customer_id)
        if query is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Query with id {query_id} not found",
            )
        return query

    async def _get_any(self, query_id: int) -> Any:
        query = await self.repository.get_by_id(query_id)
        if query is None or query.is_deleted:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Query with id {query_id} not found",
            )
        return query

    async def _commit(self, query: Any) -> None:
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(query)

    async def _generate_query_number(self, day: date) -> str:
        clean_date = day.strftime("%Y%m%d")
        for _ in range(8):
            candidate = f"QRY-{clean_date}-{secrets.token_hex(2).upper()}"
            if await self.repository.find_by_query_no(candidate) is None:
                return candidate
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Could not generate a unique query number",
        )


def _page_payload(
    rows: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "items": [serialize_customer_query(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }
