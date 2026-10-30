from __future__ import annotations

import jwt
from fastapi import Depends, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import api_error
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.buffalo_repository import BuffaloRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.delete_repository import DeleteRepository
from app.repositories.expense_category_repository import ExpenseCategoryRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.production_repository import ProductionRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.stock_repository import StockRepository
from app.repositories.user_repository import UserRepository
from app.repositories.wastage_repository import WastageRepository
from app.services.auth_service import AuthService
from app.services.buffalo_service import BuffaloService
from app.services.customer_service import CustomerService
from app.services.delete_service import DeleteService
from app.services.expense_category_service import ExpenseCategoryService
from app.services.expense_service import ExpenseService
from app.services.invoice_service import InvoiceService
from app.services.production_service import ProductionService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.stock_service import StockService
from app.services.user_service import UserService
from app.services.wastage_service import WastageService

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

    request.state.user = user
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            joined = ", ".join(roles)
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                f"Access denied: Requires one of [{joined}] role",
            )
        return user

    return dependency


require_admin = require_roles("admin")


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repository)


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(repository)


def get_buffalo_repository(db: AsyncSession = Depends(get_db)) -> BuffaloRepository:
    return BuffaloRepository(db)


def get_buffalo_service(
    repository: BuffaloRepository = Depends(get_buffalo_repository),
) -> BuffaloService:
    return BuffaloService(repository)


def get_production_repository(
    db: AsyncSession = Depends(get_db),
) -> ProductionRepository:
    return ProductionRepository(db)


def get_production_service(
    repository: ProductionRepository = Depends(get_production_repository),
    buffalo_repository: BuffaloRepository = Depends(get_buffalo_repository),
) -> ProductionService:
    return ProductionService(repository, buffalo_repository)


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
) -> WastageService:
    return WastageService(repository, stock_service)


def get_customer_repository(
    db: AsyncSession = Depends(get_db),
) -> CustomerRepository:
    return CustomerRepository(db)


def get_customer_service(
    repository: CustomerRepository = Depends(get_customer_repository),
) -> CustomerService:
    return CustomerService(repository)


def get_sale_repository(db: AsyncSession = Depends(get_db)) -> SaleRepository:
    return SaleRepository(db)


def get_sale_service(
    repository: SaleRepository = Depends(get_sale_repository),
    customer_repository: CustomerRepository = Depends(
        get_customer_repository
    ),
    stock_service: StockService = Depends(get_stock_service),
) -> SaleService:
    return SaleService(repository, customer_repository, stock_service)


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
) -> InvoiceService:
    return InvoiceService(
        repository,
        customer_repository,
        sale_repository,
    )


def get_delete_repository(db: AsyncSession = Depends(get_db)) -> DeleteRepository:
    return DeleteRepository(db)


def get_delete_service(
    repository: DeleteRepository = Depends(get_delete_repository),
) -> DeleteService:
    return DeleteService(repository)


def get_expense_category_repository(
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategoryRepository:
    return ExpenseCategoryRepository(db)


def get_expense_category_service(
    repository: ExpenseCategoryRepository = Depends(
        get_expense_category_repository
    ),
) -> ExpenseCategoryService:
    return ExpenseCategoryService(repository)


def get_expense_repository(
    db: AsyncSession = Depends(get_db),
) -> ExpenseRepository:
    return ExpenseRepository(db)


def get_expense_service(
    repository: ExpenseRepository = Depends(get_expense_repository),
    category_repository: ExpenseCategoryRepository = Depends(
        get_expense_category_repository
    ),
) -> ExpenseService:
    return ExpenseService(repository, category_repository)


def get_report_repository(db: AsyncSession = Depends(get_db)) -> ReportRepository:
    return ReportRepository(db)


def get_report_service(
    repository: ReportRepository = Depends(get_report_repository),
    buffalo_service: BuffaloService = Depends(get_buffalo_service),
    production_service: ProductionService = Depends(get_production_service),
    stock_service: StockService = Depends(get_stock_service),
) -> ReportService:
    return ReportService(
        repository,
        buffalo_service,
        production_service,
        stock_service,
    )
