from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import (
    get_current_customer_account,
    get_customer_portal_auth_service,
)
from app.core.errors import api_error
from app.models.customer_portal_account import CustomerPortalAccount
from app.schemas.customer_portal_auth import (
    ActivatePortalAccountRequest,
    CustomerLoginRequest,
)
from app.services.customer_portal_auth_service import CustomerPortalAuthService

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


@router.get("/me")
async def me(
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerPortalAuthService = Depends(get_customer_portal_auth_service),
) -> dict[str, Any]:
    return await service.get_me(account)
