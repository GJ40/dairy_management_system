from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import BackgroundTasks, status

from app.core.config import settings
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.user import User
from app.repositories.customer_order_repository import CustomerOrderRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.sale_repository import SaleRepository
from app.schemas.customer_orders import (
    ORDER_STATUSES,
    CustomerOrderQuery,
    serialize_order_detail,
    serialize_order_invoice,
    serialize_order_sale,
    serialize_order_summary,
)
from app.schemas.customer_orders_staff import (
    StaffOrderQuery,
    serialize_staff_order_detail,
    serialize_staff_order_summary,
)
from app.services.invoice_service import InvoiceService
from app.services.order_email_service import OrderEmailDispatch
from app.services.security_audit_service import SecurityAuditService
from app.services.stock_lock import StockLockService
from app.services.stock_service import StockService
from app.utils.tasks import deliver_or_queue
from app.utils.time import business_now, business_now_naive

MONEY = Decimal("0.01")

# Notification events dispatched after each transition commits.
ORDER_SUBMITTED = "order.submitted"
ORDER_APPROVED = "order.approved"
ORDER_REJECTED = "order.rejected"
ORDER_CANCELLED = "order.cancelled"
ORDER_FULFILLED = "order.fulfilled"


class CustomerOrderService:
    def __init__(
        self,
        repository: CustomerOrderRepository,
        customer_repository: CustomerRepository,
        *,
        stock_service: StockService | None = None,
        sale_repository: SaleRepository | None = None,
        invoice_service: InvoiceService | None = None,
        stock_lock: StockLockService | None = None,
        audit: SecurityAuditService | None = None,
        email_dispatch: OrderEmailDispatch | None = None,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        self.stock_service = stock_service
        self.sale_repository = sale_repository
        self.invoice_service = invoice_service
        self.stock_lock = stock_lock
        self.audit = audit
        # Optional so every existing caller (and test) keeps working: with no
        # dispatcher configured, order transitions simply send nothing.
        self.email_dispatch = email_dispatch

    async def _record(
        self,
        *,
        event_type: str,
        context: RequestContext | None,
        order_id: int,
        metadata: dict[str, object],
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
    ) -> None:
        if self.audit is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            resource_type="customer_order",
            resource_id=order_id,
            metadata=metadata,
        )

    async def _notify_order(
        self,
        event_key: str,
        order_id: int,
        background: BackgroundTasks | None,
    ) -> None:
        """Queue the order notification; only called after a commit."""
        if self.email_dispatch is None:
            return
        await deliver_or_queue(
            background,
            self.email_dispatch,
            event_key=event_key,
            order_id=order_id,
        )

    @asynccontextmanager
    async def _lock(self):
        if self.stock_lock is None:
            yield
        else:
            async with self.stock_lock.lock():
                yield

    async def create(
        self,
        account: CustomerPortalAccount,
        *,
        quantity_litres: Decimal,
        requested_date: date,
        note: str | None,
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

        self._validate_quantity(quantity_litres)

        today = business_now().date()
        latest = today + timedelta(days=settings.customer_order_window_days)
        if requested_date < today or requested_date > latest:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_REQUESTED_DATE",
                f"Requested date must be between {today.isoformat()} and "
                f"{latest.isoformat()}",
            )

        already_ordered = await self.repository.reserved_litres(
            customer_id=customer.id,
            requested_date=requested_date,
        )
        cap = Decimal(settings.customer_order_daily_cap_litres)
        if already_ordered + quantity_litres > cap:
            remaining = max(cap - already_ordered, Decimal("0.00"))
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "ORDER_DAILY_LIMIT_EXCEEDED",
                f"Daily order limit for {requested_date.isoformat()} is "
                f"{cap:.2f} L; {remaining:.2f} L remain",
            )

        rate = Decimal(customer.rate_per_litre or 0)
        if rate <= 0:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Customer milk rate is not configured",
            )
        estimated_total = (quantity_litres * rate).quantize(
            MONEY,
            rounding=ROUND_HALF_UP,
        )

        order_no = await self._generate_order_number(today)
        order = await self.repository.create(
            order_no=order_no,
            customer_id=customer.id,
            account_id=account.id,
            requested_date=requested_date,
            quantity_litres=quantity_litres,
            rate_snapshot=rate.quantize(MONEY),
            estimated_total=estimated_total,
            note=note,
        )
        await self.repository.add_event(
            order_id=order.id,
            from_status=None,
            to_status="submitted",
            actor_type="customer",
            actor_account_id=account.id,
        )

        try:
            await self._record(
                event_type="order.created",
                context=context,
                actor_account_id=account.id,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "order_no": order.order_no,
                    "customer_id": order.customer_id,
                    "requested_date": order.requested_date,
                    "quantity_litres": order.quantity_litres,
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(order)

        await self._notify_order(ORDER_SUBMITTED, order.id, background)
        return {"order": serialize_order_summary(order)}

    async def list_orders(
        self,
        account: CustomerPortalAccount,
        query: CustomerOrderQuery,
    ) -> dict[str, Any]:
        if query.status is not None and query.status not in ORDER_STATUSES:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "status: Invalid order status",
            )
        if (
            query.from_date is not None
            and query.to_date is not None
            and query.from_date > query.to_date
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "from: must be on or before to",
            )

        rows, total = await self.repository.list_and_count(
            customer_id=account.customer_id,
            page=query.page,
            page_size=query.page_size,
            status=query.status,
            from_date=query.from_date,
            to_date=query.to_date,
        )
        return {
            "items": [serialize_order_summary(order) for order in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def get_order(
        self,
        account: CustomerPortalAccount,
        order_id: int,
    ) -> dict[str, Any]:
        order = await self._get_owned(account, order_id)
        events = await self.repository.list_events(order.id)
        sale = await self.repository.get_sale_by_order_id(order.id)
        invoice = (
            await self.repository.get_invoice_for_sale(sale.id) if sale else None
        )
        return {
            "order": serialize_order_detail(
                order,
                events=events,
                sale=sale,
                invoice=invoice,
            )
        }

    async def cancel(
        self,
        account: CustomerPortalAccount,
        order_id: int,
        reason: str | None,
        *,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        order = await self._get_owned(account, order_id)
        if order.status != "submitted":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "INVALID_ORDER_TRANSITION",
                f"Orders in status '{order.status}' cannot be cancelled",
            )

        order.status = "cancelled"
        order.reason = reason
        await self.repository.add_event(
            order_id=order.id,
            from_status="submitted",
            to_status="cancelled",
            actor_type="customer",
            actor_account_id=account.id,
            reason=reason,
        )

        try:
            await self._record(
                event_type="order.cancelled",
                context=context,
                actor_account_id=account.id,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "from_status": "submitted",
                    "to_status": "cancelled",
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(order)

        await self._notify_order(ORDER_CANCELLED, order.id, background)
        return {"order": serialize_order_summary(order)}

    async def staff_list_orders(self, query: StaffOrderQuery) -> dict[str, Any]:
        if query.status is not None and query.status not in ORDER_STATUSES:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "status: Invalid order status",
            )
        if (
            query.from_date is not None
            and query.to_date is not None
            and query.from_date > query.to_date
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "from: must be on or before to",
            )
        if query.search is not None and len(query.search.strip()) > 100:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "search: must be at most 100 characters",
            )

        rows, total = await self.repository.list_all_and_count(
            page=query.page,
            page_size=query.page_size,
            status=query.status,
            customer_id=query.customer_id,
            from_date=query.from_date,
            to_date=query.to_date,
            search=query.search,
        )
        customers: dict[int, Any] = {}
        items = []
        for order in rows:
            customer = customers.get(order.customer_id)
            if customer is None:
                customer = await self.customer_repository.get_by_id(
                    order.customer_id
                )
                customers[order.customer_id] = customer
            account = await self.repository.get_account(order.account_id)
            items.append(
                serialize_staff_order_summary(
                    order,
                    customer=customer,
                    account=account,
                )
            )
        return {
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def staff_get_order(self, order_id: int) -> dict[str, Any]:
        order = await self._get_any(order_id)
        return {"order": await self._staff_detail(order)}

    async def approve(
        self,
        user: User,
        order_id: int,
        note: str | None,
        *,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        async with self._lock():
            order = await self._get_any(order_id)
            if order.status != "submitted":
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "INVALID_ORDER_TRANSITION",
                    f"Orders in status '{order.status}' cannot be approved",
                )

            await self._assert_stock_available(order)

            order.status = "approved"
            order.reviewed_by = user.id
            order.reviewed_at = business_now_naive()
            await self.repository.add_event(
                order_id=order.id,
                from_status="submitted",
                to_status="approved",
                actor_type=user.role,
                actor_user_id=user.id,
                reason=note,
            )
            await self._commit(
                order,
                audit_event={
                    "event_type": "order.approved",
                    "context": context,
                    "actor_user_id": user.id,
                    "metadata": {
                        "order_id": order.id,
                        "from_status": "submitted",
                        "to_status": "approved",
                    },
                },
            )

        # Queued after the lock is released: an inline send would otherwise run
        # SMTP while the stock lock (and its transaction) is still held.
        await self._notify_order(ORDER_APPROVED, order.id, background)
        return {"order": await self._staff_detail(order)}

    async def reject(
        self,
        user: User,
        order_id: int,
        reason: str,
        *,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        order = await self._get_any(order_id)
        if order.status != "submitted":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "INVALID_ORDER_TRANSITION",
                f"Orders in status '{order.status}' cannot be rejected",
            )

        order.status = "rejected"
        order.reason = reason
        order.reviewed_by = user.id
        order.reviewed_at = business_now_naive()
        await self.repository.add_event(
            order_id=order.id,
            from_status="submitted",
            to_status="rejected",
            actor_type=user.role,
            actor_user_id=user.id,
            reason=reason,
        )
        await self._commit(
            order,
            audit_event={
                "event_type": "order.rejected",
                "context": context,
                "actor_user_id": user.id,
                "metadata": {
                    "order_id": order.id,
                    "from_status": "submitted",
                    "to_status": "rejected",
                },
            },
        )
        await self._notify_order(ORDER_REJECTED, order.id, background)
        return {"order": await self._staff_detail(order)}

    async def fulfil(
        self,
        user: User,
        order_id: int,
        *,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        async with self._lock():
            order = await self._get_any(order_id)
            if order.status != "approved":
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "INVALID_ORDER_TRANSITION",
                    f"Orders in status '{order.status}' cannot be fulfilled",
                )

            today = business_now().date()
            if order.requested_date > today or (
                user.role == "operator" and order.requested_date != today
            ):
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_FULFILMENT_DATE",
                    "Operators may fulfil only orders requested for today; "
                    "Admins may fulfil today or past orders",
                )

            if self.sale_repository is None or self.invoice_service is None:
                raise RuntimeError("Fulfilment dependencies are not configured")

            sale = await self.sale_repository.create(
                customer_id=order.customer_id,
                sale_date=order.requested_date,
                litres=order.quantity_litres,
                rate=order.rate_snapshot,
                amount=order.estimated_total,
                recorded_by=user.id,
                source_order_id=order.id,
            )
            await self.sale_repository.flush()
            invoice = await self.invoice_service.create_invoice_for_sale(
                customer_id=order.customer_id,
                sale_id=sale.id,
                period_start=order.requested_date,
                period_end=order.requested_date,
                total_amount=order.estimated_total,
            )

            order.status = "fulfilled"
            await self.repository.add_event(
                order_id=order.id,
                from_status="approved",
                to_status="fulfilled",
                actor_type=user.role,
                actor_user_id=user.id,
            )
            await self._commit(
                order,
                audit_event={
                    "event_type": "order.fulfilled",
                    "context": context,
                    "actor_user_id": user.id,
                    "metadata": {
                        "order_id": order.id,
                        "sale_id": sale.id,
                        "invoice_id": invoice.id,
                        "amount": order.estimated_total,
                    },
                },
            )

        await self._notify_order(ORDER_FULFILLED, order.id, background)
        detail = await self._staff_detail(order)
        return {
            "order": detail,
            "sale": serialize_order_sale(sale),
            "invoice": serialize_order_invoice(invoice),
        }

    async def staff_cancel(
        self,
        user: User,
        order_id: int,
        reason: str,
        *,
        context: RequestContext | None = None,
        background: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        async with self._lock():
            order = await self._get_any(order_id)
            if order.status not in ("submitted", "approved"):
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "INVALID_ORDER_TRANSITION",
                    f"Orders in status '{order.status}' cannot be cancelled",
                )

            previous = order.status
            order.status = "cancelled"
            order.reason = reason
            order.reviewed_by = user.id
            order.reviewed_at = business_now_naive()
            await self.repository.add_event(
                order_id=order.id,
                from_status=previous,
                to_status="cancelled",
                actor_type=user.role,
                actor_user_id=user.id,
                reason=reason,
            )
            await self._commit(
                order,
                audit_event={
                    "event_type": "order.cancelled",
                    "context": context,
                    "actor_user_id": user.id,
                    "metadata": {
                        "order_id": order.id,
                        "from_status": previous,
                        "to_status": "cancelled",
                    },
                },
            )

        await self._notify_order(ORDER_CANCELLED, order.id, background)
        return {"order": await self._staff_detail(order)}

    async def _assert_stock_available(self, order: Any) -> None:
        if self.stock_service is None:
            raise RuntimeError("Stock service is not configured")
        await self.stock_service.assert_available_stock(
            order.requested_date.isoformat(),
            order.quantity_litres,
            reserved_lookup=self.repository.total_approved_litres,
        )

    async def _staff_detail(self, order: Any) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(order.customer_id)
        account = await self.repository.get_account(order.account_id)
        events = await self.repository.list_events(order.id)
        sale = await self.repository.get_sale_by_order_id(order.id)
        invoice = (
            await self.repository.get_invoice_for_sale(sale.id) if sale else None
        )
        return serialize_staff_order_detail(
            order,
            customer=customer,
            account=account,
            events=events,
            sale=sale,
            invoice=invoice,
        )

    async def _commit(
        self,
        order: Any,
        *,
        audit_event: dict[str, Any] | None = None,
    ) -> None:
        try:
            if audit_event is not None:
                await self._record(order_id=order.id, **audit_event)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(order)

    async def _get_any(self, order_id: int) -> Any:
        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Order with id {order_id} not found",
            )
        return order

    async def _get_owned(
        self,
        account: CustomerPortalAccount,
        order_id: int,
    ):
        order = await self.repository.get_owned(order_id, account.customer_id)
        if order is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Order with id {order_id} not found",
            )
        return order

    @staticmethod
    def _validate_quantity(quantity: Decimal) -> None:
        if quantity <= 0:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_QUANTITY",
                "Quantity must be greater than zero",
            )
        minimum = Decimal(settings.customer_order_min_litres)
        maximum = Decimal(settings.customer_order_max_litres)
        if quantity < minimum or quantity > maximum:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "ORDER_LIMIT_EXCEEDED",
                f"Quantity must be between {minimum:.2f} L and {maximum:.2f} L",
            )

    async def _generate_order_number(self, day: date) -> str:
        clean_date = day.strftime("%Y%m%d")
        for _ in range(8):
            candidate = f"ORD-{clean_date}-{secrets.token_hex(2).upper()}"
            if await self.repository.find_by_order_no(candidate) is None:
                return candidate
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Could not generate a unique order number",
        )
