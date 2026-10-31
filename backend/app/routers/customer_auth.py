from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import (
    get_current_customer_account,
    get_customer_portal_auth_service,
    get_password_reset_service,
)
from app.core.errors import api_error
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.password_reset_token import RESET_SCOPE_CUSTOMER
from app.schemas.customer_portal_auth import (
    ActivatePortalAccountRequest,
    CustomerLoginRequest,
)
from app.schemas.password_reset import ForgotPasswordRequest, ResetPasswordRequest
from app.services.customer_portal_auth_service import CustomerPortalAuthService
from app.services.password_reset_service import PasswordResetService

router = APIRouter(prefix="/customer-auth", tags=["customer-auth"])


def _set_customer_cookies(response: Response, refresh_token: str) -> None:
    max_age = settings.customer_refresh_cookie_max_age
    response.set_cookie(
        value=refresh_token,
        max_age=max_age,
        **settings.customer_refresh_cookie_flags,
    )
    response.set_cookie(
        value="1",
        max_age=max_age,
        **settings.customer_session_hint_cookie_flags,
    )


def _delete_cookie(response: Response, flags: dict[str, object]) -> None:
    response.delete_cookie(
        key=flags["key"],
        path=flags["path"],
        domain=flags["domain"],
        secure=flags["secure"],
        httponly=flags["httponly"],
        samesite=flags["samesite"],
    )


def _clear_customer_cookies(response: Response) -> None:
    _delete_cookie(response, settings.customer_refresh_cookie_flags)
    _delete_cookie(response, settings.customer_session_hint_cookie_flags)


def _error_with_cookies(exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = str(detail.get("code") or "UNAUTHORIZED")
    message = str(detail.get("message") or exc.detail)
    response = JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )
    _clear_customer_cookies(response)
    return response


@router.post(
    "/activate",
    summary="Activate a customer portal account",
    description=(
        "Consumes a single-use activation token issued by dairy staff and sets "
        "the customer's password. No session is created; sign in afterwards."
    ),
)
async def activate(
    payload: ActivatePortalAccountRequest,
    service: CustomerPortalAuthService = Depends(get_customer_portal_auth_service),
) -> dict[str, Any]:
    return await service.activate(payload.token, payload.password)


@router.post(
    "/login",
    summary="Sign in to the customer portal",
    description=(
        "Returns a short-lived customer access token plus the account profile. "
        "The refresh token is delivered only as the httpOnly "
        "`dairy_customer_refresh_token` cookie."
    ),
)
async def login(
    payload: CustomerLoginRequest,
    response: Response,
    service: CustomerPortalAuthService = Depends(get_customer_portal_auth_service),
) -> dict[str, Any]:
    session = await service.login(payload.email, payload.password)
    _set_customer_cookies(response, session.pop("refresh_token"))
    return session


@router.post("/refresh")
async def refresh(
    request: Request,
    service: CustomerPortalAuthService = Depends(get_customer_portal_auth_service),
) -> Any:
    refresh_token = request.cookies.get(settings.customer_refresh_cookie_name)
    if not refresh_token:
        return _error_with_cookies(
            api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Refresh token not provided",
            )
        )
    try:
        return await service.refresh(refresh_token)
    except HTTPException as exc:
        return _error_with_cookies(exc)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    _clear_customer_cookies(response)
    return {"message": "Logged out"}


@router.post(
    "/forgot-password",
    summary="Request a customer portal password reset link",
    description=(
        "Always returns the same message. A single-use link is emailed only when "
        "an activated portal account exists for the address."
    ),
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background: BackgroundTasks,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    return await service.request_customer_reset(
        payload.email, background=background
    )


@router.get(
    "/reset-password/validate",
    summary="Check a customer password reset link",
)
async def validate_reset_password(
    token: str = Query(default="", max_length=200),
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, bool]:
    return await service.validate(RESET_SCOPE_CUSTOMER, token)


@router.post(
    "/reset-password",
    summary="Set a new customer portal password from a reset link",
)
async def reset_password(
    payload: ResetPasswordRequest,
    background: BackgroundTasks,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    return await service.reset_password(
        RESET_SCOPE_CUSTOMER,
        payload.token,
        payload.password,
        background=background,
    )


@router.get("/me")
async def me(
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerPortalAuthService = Depends(get_customer_portal_auth_service),
) -> dict[str, Any]:
    return await service.get_me(account)
