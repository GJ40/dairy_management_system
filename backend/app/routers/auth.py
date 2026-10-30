from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import get_auth_service, get_current_user
from app.core.errors import api_error
from app.models.user import User
from app.schemas.user import LoginRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _legacy_refresh_path() -> str:
    """The auth-only path older builds scoped the cookie to.

    A browser that still holds that cookie sends two `dairy_refresh_token`
    values to `/auth/refresh`, and the stale one can win, so it is dropped.
    """
    return f"{settings.api_v1_prefix.rstrip('/')}/auth"


def _set_session_cookies(response: Response, token: str) -> None:
    max_age = settings.refresh_cookie_max_age
    # The refresh token itself is unreadable from JavaScript...
    response.set_cookie(value=token, max_age=max_age, **settings.refresh_cookie_flags)
    # ...this flag only says "a session probably exists", so the SPA can skip
    # the refresh probe when a visitor has never signed in.
    response.set_cookie(value="1", max_age=max_age, **settings.session_hint_cookie_flags)
    legacy_path = _legacy_refresh_path()
    if legacy_path != settings.refresh_cookie_path:
        # Drop the narrower cookie an older build left behind (different path).
        _delete_cookie(response, settings.refresh_cookie_flags, path=legacy_path)


def _delete_cookie(
    response: Response,
    flags: dict[str, object],
    path: str | None = None,
) -> None:
    response.delete_cookie(
        key=flags["key"],
        path=path or flags["path"],
        domain=flags["domain"],
        secure=flags["secure"],
        httponly=flags["httponly"],
        samesite=flags["samesite"],
    )


def _clear_session_cookies(response: Response) -> None:
    _delete_cookie(response, settings.refresh_cookie_flags)
    legacy_path = _legacy_refresh_path()
    if legacy_path != settings.refresh_cookie_path:
        _delete_cookie(response, settings.refresh_cookie_flags, path=legacy_path)
    _delete_cookie(response, settings.session_hint_cookie_flags)


def _error_with_cookies(exc: HTTPException) -> JSONResponse:
    """Reject the refresh and drop the session cookies in the same response.

    Raising instead would hand the error to the exception handler, which builds
    a brand-new response and silently discards cookies set on the injected one.
    """
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = str(detail.get("code") or "UNAUTHORIZED")
    message = str(detail.get("message") or exc.detail)
    response = JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )
    _clear_session_cookies(response)
    return response


@router.post(
    "/login",
    summary="Sign in",
    description=(
        "Returns `access_token` (a short-lived JWT for the `BearerAuth` field) "
        "plus the user profile. The refresh token is **not** in this JSON body: "
        "it is delivered as the httpOnly `dairy_refresh_token` cookie and cannot "
        "be read by JavaScript. Note that browsers hide `Set-Cookie` from "
        "JavaScript, so Swagger UI will never show it under Response headers; "
        "open DevTools > Application > Cookies to inspect it. To test the "
        "refresh here, just Execute POST /auth/refresh — the browser sends the "
        "cookie on its own, and the route takes no parameters."
    ),
)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    session = await service.login(payload.email, payload.password)
    # The refresh token only ever leaves the API as an httpOnly cookie.
    _set_session_cookies(response, session.pop("refresh_token"))
    return session


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token",
    description=(
        "Uses the httpOnly `dairy_refresh_token` cookie only: browsers send it "
        "automatically, so in Swagger UI you can Execute this straight after "
        "logging in (the cookie's path is `/api/v1`, so it applies here), "
        "and the route has no parameters, request body or `Authorization` "
        "header. Only `access_token` plus the user profile come back, and a "
        "cookie holding an access token is rejected."
    ),
)
async def refresh(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    # The refresh token is delivered and read only as the httpOnly cookie.
    refresh_token = request.cookies.get(settings.refresh_cookie_name)

    if not refresh_token:
        # Nothing to refresh with, so any leftover hint cookie is stale.
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
        # It was our cookie, so a rejected session must not linger.
        return _error_with_cookies(exc)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    _clear_session_cookies(response)
    return {"message": "Logged out"}


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    return {"user": await service.get_me(current_user.id)}
