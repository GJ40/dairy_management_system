from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import Depends, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.core.security import decode_access_token, decode_customer_access_token
from app.db.session import SessionLocal, engine, get_db
from app.models.customer import Customer
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.user import User
from app.repositories.buffalo_repository import BuffaloRepository
from app.repositories.customer_order_repository import CustomerOrderRepository
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_query_repository import CustomerQueryRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.delete_repository import DeleteRepository
from app.repositories.expense_category_repository import ExpenseCategoryRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.production_repository import ProductionRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.security_audit_repository import SecurityAuditRepository
from app.repositories.stock_repository import StockRepository
from app.repositories.user_repository import UserRepository
from app.repositories.wastage_repository import WastageRepository
from app.services.auth_service import AuthService
from app.services.buffalo_service import BuffaloService
from app.services.customer_dashboard_service import CustomerDashboardService
from app.services.customer_invoice_service import CustomerInvoiceService
from app.services.customer_order_service import CustomerOrderService
from app.services.customer_portal_auth_service import (
    CustomerPortalAccountService,
    CustomerPortalAuthService,
)
from app.services.customer_query_service import CustomerQueryService
from app.services.customer_service import CustomerService
from app.services.delete_service import DeleteService
from app.services.email_service import EmailService
from app.services.expense_category_service import ExpenseCategoryService
from app.services.expense_service import ExpenseService
from app.services.invoice_service import InvoiceService
from app.services.login_security_service import LoginSecurityService
from app.services.password_reset_service import PasswordResetService
from app.services.production_service import ProductionService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.security_audit_service import SecurityAuditService
from app.services.stock_lock import StockLockService
from app.services.stock_service import StockService
from app.services.user_service import UserService
from app.services.wastage_service import WastageService


def _token_version(payload: dict[str, Any]) -> int:
    """Read the session version a token was signed with.

    Tokens issued before this claim existed decode as version 0, which matches
    every row until a password reset or deactivation bumps it.
    """
    try:
        return int(payload.get("ver", 0))
    except (TypeError, ValueError):
        return -1


bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description=(
        "Short-lived access token from POST /api/v1/auth/login (or "
        "POST /api/v1/auth/refresh). Paste the token only; Swagger sends it as "
        "'Authorization: Bearer <token>'. Every guard also requires the httpOnly "
        "dairy_refresh_token session cookie, so sign in through POST "
        "/api/v1/auth/login in this browser before calling protected routes. "
        "Refresh tokens are not accepted here."
    ),
    auto_error=False,
)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User:
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Missing or malformed Authorization header",
        )

    token = auth_header[7:].strip()
    if not token:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication token not provided",
        )

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid authentication token",
        ) from exc

    # A bare access token is not a session: the httpOnly refresh cookie is the
    # half that proves the browser still holds one. Removing that cookie signs
    # the session out immediately, even while the access token is still valid.
    if not request.cookies.get(settings.refresh_cookie_name):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Refresh token cookie is missing; sign in again",
        )

    try:
        user_id = int(payload.get("id"))
    except (TypeError, ValueError) as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "User account not found",
        ) from exc

    user = await db.get(User, user_id)
    if user is None or user.is_deleted:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "User account not found",
        )
    if not user.is_active:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "User account is deactivated",
        )
    if _token_version(payload) != (user.token_version or 0):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Session has expired; sign in again",
        )

    request.state.user = user
    return user


logger = logging.getLogger("app.security.audit")


def require_roles(*roles: str):
    async def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        audit: SecurityAuditService = Depends(get_security_audit_service),
    ) -> User:
        if user.role not in roles:
            joined = ", ".join(roles)
            try:
                await audit.record_standalone(
                    event_type="security.authorization.denied",
                    context=get_request_context(request),
                    actor_user_id=user.id,
                    resource_type="endpoint",
                    resource_id=request.url.path,
                    metadata={
                        "required_roles": list(roles),
                        "actual_role": user.role,
                        "scope": request.url.path,
                    },
                )
            except Exception:
                logger.exception(
                    "Security audit write failed (event_type=%s)",
                    "security.authorization.denied",
                )
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                f"Access denied: Requires one of [{joined}] role",
            )
        return user

    return dependency


customer_bearer_scheme = HTTPBearer(
    scheme_name="CustomerBearerAuth",
    description=(
        "Short-lived customer access token from POST /api/v1/customer-auth/login "
        "(or /customer-auth/refresh). Every customer guard also requires the "
        "httpOnly dairy_customer_refresh_token cookie, which is separate from "
        "the staff session cookie."
    ),
    auto_error=False,
)


async def get_current_customer_account(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _credentials: HTTPAuthorizationCredentials | None = Security(
        customer_bearer_scheme
    ),
) -> CustomerPortalAccount:
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Missing or malformed Authorization header",
        )

    token = auth_header[7:].strip()
    if not token:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication token not provided",
        )

    try:
        payload = decode_customer_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid authentication token",
        ) from exc

    if not request.cookies.get(settings.customer_refresh_cookie_name):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Customer session cookie is missing; sign in again",
        )

    try:
        account_id = int(payload.get("account_id"))
    except (TypeError, ValueError) as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Account not found",
        ) from exc

    account = await db.get(CustomerPortalAccount, account_id)
    if (
        account is None
        or account.is_deleted
        or account.activated_at is None
        or not account.password_hash
    ):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Account not found",
        )
    if not account.is_active:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "ACCOUNT_INACTIVE",
            "This portal account is deactivated",
        )

    customer = await db.get(Customer, account.customer_id)
    if customer is None or customer.is_deleted:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Account not found",
        )
    if not customer.is_active:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "ACCOUNT_INACTIVE",
            "The linked customer account is inactive",
        )
    if _token_version(payload) != (account.token_version or 0):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Session has expired; sign in again",
        )

    request.state.customer_account = account
    return account


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_email_service() -> EmailService:
    return EmailService()


def get_security_audit_service(
    db: AsyncSession = Depends(get_db),
) -> SecurityAuditService:
    return SecurityAuditService(
        SecurityAuditRepository(db),
        standalone_session_factory=SessionLocal,
    )


# Defined after get_security_audit_service because require_roles() binds that
# dependency when the factory runs.
require_admin = require_roles("admin")


def get_login_security_service(
    audit: SecurityAuditService = Depends(get_security_audit_service),
    email_service: EmailService = Depends(get_email_service),
) -> LoginSecurityService:
    return LoginSecurityService(audit, email_service)


def get_auth_service(
    repository: UserRepository = Depends(get_user_repository),
    login_security: LoginSecurityService = Depends(get_login_security_service),
) -> AuthService:
    return AuthService(repository, login_security)


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> UserService:
    return UserService(repository, audit)


def get_buffalo_repository(db: AsyncSession = Depends(get_db)) -> BuffaloRepository:
    return BuffaloRepository(db)


def get_buffalo_service(
    repository: BuffaloRepository = Depends(get_buffalo_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> BuffaloService:
    return BuffaloService(repository, audit=audit)


def get_production_repository(
    db: AsyncSession = Depends(get_db),
) -> ProductionRepository:
    return ProductionRepository(db)


def get_production_service(
    repository: ProductionRepository = Depends(get_production_repository),
    buffalo_repository: BuffaloRepository = Depends(get_buffalo_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> ProductionService:
    return ProductionService(repository, buffalo_repository, audit=audit)


def get_stock_repository(db: AsyncSession = Depends(get_db)) -> StockRepository:
    return StockRepository(db)


def get_stock_service(
    repository: StockRepository = Depends(get_stock_repository),
) -> StockService:
    return StockService(repository)


def get_wastage_repository(db: AsyncSession = Depends(get_db)) -> WastageRepository:
    return WastageRepository(db)


def get_wastage_service(
    repository: WastageRepository = Depends(get_wastage_repository),
    stock_service: StockService = Depends(get_stock_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> WastageService:
    return WastageService(repository, stock_service, audit=audit)


def get_customer_repository(
    db: AsyncSession = Depends(get_db),
) -> CustomerRepository:
    return CustomerRepository(db)


def get_customer_service(
    repository: CustomerRepository = Depends(get_customer_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerService:
    return CustomerService(repository, audit)


def get_sale_repository(db: AsyncSession = Depends(get_db)) -> SaleRepository:
    return SaleRepository(db)


def get_customer_order_repository(
    db: AsyncSession = Depends(get_db),
) -> CustomerOrderRepository:
    return CustomerOrderRepository(db)


def get_stock_lock_service() -> StockLockService:
    return StockLockService(engine)


def get_sale_service(
    repository: SaleRepository = Depends(get_sale_repository),
    customer_repository: CustomerRepository = Depends(
        get_customer_repository
    ),
    stock_service: StockService = Depends(get_stock_service),
    stock_lock: StockLockService = Depends(get_stock_lock_service),
    order_repository: CustomerOrderRepository = Depends(
        get_customer_order_repository
    ),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> SaleService:
    return SaleService(
        repository,
        customer_repository,
        stock_service,
        stock_lock=stock_lock,
        order_repository=order_repository,
        audit=audit,
    )


def get_invoice_repository(
    db: AsyncSession = Depends(get_db),
) -> InvoiceRepository:
    return InvoiceRepository(db)


def get_invoice_service(
    repository: InvoiceRepository = Depends(get_invoice_repository),
    customer_repository: CustomerRepository = Depends(
        get_customer_repository
    ),
    sale_repository: SaleRepository = Depends(get_sale_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> InvoiceService:
    return InvoiceService(
        repository,
        customer_repository,
        sale_repository,
        audit=audit,
    )


def get_customer_invoice_service(
    repository: InvoiceRepository = Depends(get_invoice_repository),
    customer_repository: CustomerRepository = Depends(
        get_customer_repository
    ),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerInvoiceService:
    return CustomerInvoiceService(repository, customer_repository, audit=audit)


def get_delete_repository(db: AsyncSession = Depends(get_db)) -> DeleteRepository:
    return DeleteRepository(db)


def get_delete_service(
    repository: DeleteRepository = Depends(get_delete_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> DeleteService:
    return DeleteService(repository, audit)


def get_expense_category_repository(
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategoryRepository:
    return ExpenseCategoryRepository(db)


def get_expense_category_service(
    repository: ExpenseCategoryRepository = Depends(
        get_expense_category_repository
    ),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> ExpenseCategoryService:
    return ExpenseCategoryService(repository, audit)


def get_expense_repository(
    db: AsyncSession = Depends(get_db),
) -> ExpenseRepository:
    return ExpenseRepository(db)


def get_expense_service(
    repository: ExpenseRepository = Depends(get_expense_repository),
    category_repository: ExpenseCategoryRepository = Depends(
        get_expense_category_repository
    ),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> ExpenseService:
    return ExpenseService(repository, category_repository, audit=audit)


def get_report_repository(db: AsyncSession = Depends(get_db)) -> ReportRepository:
    return ReportRepository(db)


def get_report_service(
    repository: ReportRepository = Depends(get_report_repository),
    buffalo_service: BuffaloService = Depends(get_buffalo_service),
    production_service: ProductionService = Depends(get_production_service),
    stock_service: StockService = Depends(get_stock_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> ReportService:
    return ReportService(
        repository,
        buffalo_service,
        production_service,
        stock_service,
        audit=audit,
    )


def get_customer_portal_account_repository(
    db: AsyncSession = Depends(get_db),
) -> CustomerPortalAccountRepository:
    return CustomerPortalAccountRepository(db)


def get_customer_portal_auth_service(
    repository: CustomerPortalAccountRepository = Depends(
        get_customer_portal_account_repository
    ),
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    login_security: LoginSecurityService = Depends(get_login_security_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerPortalAuthService:
    return CustomerPortalAuthService(
        repository,
        customer_repository,
        login_security,
        audit,
    )


def get_customer_portal_account_service(
    repository: CustomerPortalAccountRepository = Depends(
        get_customer_portal_account_repository
    ),
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    email_service: EmailService = Depends(get_email_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerPortalAccountService:
    return CustomerPortalAccountService(
        repository,
        customer_repository,
        email_service,
        audit,
    )


def get_password_reset_repository(
    db: AsyncSession = Depends(get_db),
) -> PasswordResetRepository:
    return PasswordResetRepository(db)


def get_password_reset_service(
    repository: PasswordResetRepository = Depends(get_password_reset_repository),
    user_repository: UserRepository = Depends(get_user_repository),
    account_repository: CustomerPortalAccountRepository = Depends(
        get_customer_portal_account_repository
    ),
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    email_service: EmailService = Depends(get_email_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> PasswordResetService:
    return PasswordResetService(
        repository,
        user_repository,
        account_repository,
        customer_repository,
        email_service,
        audit,
    )


def get_customer_order_service(
    repository: CustomerOrderRepository = Depends(get_customer_order_repository),
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    stock_service: StockService = Depends(get_stock_service),
    stock_lock: StockLockService = Depends(get_stock_lock_service),
    sale_repository: SaleRepository = Depends(get_sale_repository),
    invoice_service: InvoiceService = Depends(get_invoice_service),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerOrderService:
    return CustomerOrderService(
        repository,
        customer_repository,
        stock_service=stock_service,
        sale_repository=sale_repository,
        invoice_service=invoice_service,
        stock_lock=stock_lock,
        audit=audit,
    )


def get_customer_query_repository(
    db: AsyncSession = Depends(get_db),
) -> CustomerQueryRepository:
    return CustomerQueryRepository(db)


def get_customer_dashboard_service(
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    order_repository: CustomerOrderRepository = Depends(
        get_customer_order_repository
    ),
    invoice_repository: InvoiceRepository = Depends(get_invoice_repository),
    query_repository: CustomerQueryRepository = Depends(
        get_customer_query_repository
    ),
) -> CustomerDashboardService:
    return CustomerDashboardService(
        customer_repository,
        order_repository,
        invoice_repository,
        query_repository,
    )


def get_customer_query_service(
    repository: CustomerQueryRepository = Depends(
        get_customer_query_repository
    ),
    customer_repository: CustomerRepository = Depends(get_customer_repository),
    account_repository: CustomerPortalAccountRepository = Depends(
        get_customer_portal_account_repository
    ),
    user_repository: UserRepository = Depends(get_user_repository),
    audit: SecurityAuditService = Depends(get_security_audit_service),
) -> CustomerQueryService:
    return CustomerQueryService(
        repository,
        customer_repository,
        account_repository,
        user_repository,
        audit,
    )
