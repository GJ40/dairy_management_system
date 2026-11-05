from __future__ import annotations

from typing import Any

import jwt
from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import serialize_user
from app.services.login_lockout import (
    FailureOutcome,
    cooldown_error,
    cooldown_remaining_seconds,
    is_locked,
    locked_error,
    register_failed_attempt,
    reset_failed_attempts,
)
from app.services.login_security_service import STAFF_SCOPE, LoginSecurityService


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        login_security: LoginSecurityService | None = None,
    ) -> None:
        self.repository = repository
        self.login_security = login_security

    async def login(
        self,
        email: str,
        password: str,
        *,
        background: BackgroundTasks | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        user = await self.repository.get_by_email(email, include_deleted=True)
        if user is None:
            await self._record_failure(
                reason_code="unknown_email",
                context=context,
                background=background,
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid email or password",
            )

        if user.is_deleted:
            await self._record_failure(
                reason_code="deleted",
                context=context,
                background=background,
                user=user,
                alertable=False,
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid email or password",
            )

        if is_locked(user):
            # A restricted account cannot sign in even with the right password.
            # Manual deactivation and an automatic lock both land here.
            await self._record_failure(
                reason_code="account_locked",
                context=context,
                background=background,
                user=user,
                alertable=False,
            )
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_LOCKED",
                "This account is locked. Contact an administrator to unlock it.",
            )

        cooldown_seconds = cooldown_remaining_seconds(user)
        if cooldown_seconds:
            # The attempt is refused without checking the password and is not
            # counted: the cooldown is a pause, so hammering it cannot escalate
            # into a hard lock. Only a real password check advances the counter.
            await self._record_failure(
                reason_code="cooldown",
                context=context,
                background=background,
                user=user,
                alertable=False,
            )
            raise cooldown_error(cooldown_seconds)

        if not verify_password(password, user.password_hash):
            outcome = register_failed_attempt(user)
            await self._commit_lockout_state()
            await self._record_failure(
                reason_code="bad_password",
                context=context,
                background=background,
                user=user,
                alertable=True,
            )
            if outcome.locked:
                await self._notify_locked(outcome, user, context, background)
                raise locked_error()
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid email or password",
            )

        if not user.is_active:
            await self._record_failure(
                reason_code="inactive",
                context=context,
                background=background,
                user=user,
                alertable=True,
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is deactivated. Please contact an administrator.",
            )

        if user.failed_login_count or user.failed_login_first_at:
            reset_failed_attempts(user)
            await self._commit_lockout_state()

        await self._record_success(user, context, background)
        return self._issue_session(user)

    async def _commit_lockout_state(self) -> None:
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

    async def _notify_locked(
        self,
        outcome: FailureOutcome,
        user: User,
        context: RequestContext | None,
        background: BackgroundTasks | None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_account_locked(
            scope=STAFF_SCOPE,
            failure_count=outcome.count,
            context=context,
            actor_user_id=user.id,
            email=user.email,
            name=user.full_name,
            background=background,
        )

    async def _record_failure(
        self,
        *,
        reason_code: str,
        context: RequestContext | None,
        background: BackgroundTasks | None,
        user: User | None = None,
        alertable: bool = False,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_failure(
            scope=STAFF_SCOPE,
            reason_code=reason_code,
            context=context,
            actor_user_id=user.id if user is not None else None,
            email=user.email if user is not None else None,
            name=user.full_name if user is not None else None,
            alertable=alertable,
            background=background,
        )

    async def _record_success(
        self,
        user: User,
        context: RequestContext | None,
        background: BackgroundTasks | None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_success(
            scope=STAFF_SCOPE,
            context=context,
            actor_user_id=user.id,
            role=user.role,
            background=background,
        )

    async def refresh(
        self,
        refresh_token: str,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        try:
            payload = decode_refresh_token(refresh_token)
        except jwt.ExpiredSignatureError as exc:
            await self.record_refresh_failure("expired", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Refresh token has expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            await self.record_refresh_failure("invalid", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                self._invalid_refresh_message(refresh_token),
            ) from exc

        try:
            user_id = int(payload.get("id"))
        except (TypeError, ValueError) as exc:
            await self.record_refresh_failure("subject_missing", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "User account not found",
            ) from exc

        user = await self.repository.get_by_id(user_id, include_deleted=True)
        if user is None or user.is_deleted:
            await self.record_refresh_failure(
                "subject_missing",
                context,
                user_id=user_id if user is not None else None,
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "User account not found",
            )
        if not user.is_active:
            await self.record_refresh_failure(
                "inactive", context, user_id=user.id
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "User account is deactivated",
            )
        try:
            self._assert_session_current(payload, user)
        except HTTPException:
            await self.record_refresh_failure(
                "version_mismatch", context, user_id=user.id
            )
            raise

        return {
            # Named explicitly: the refresh token is not in this body, it lives
            # in the httpOnly `diary_refresh_token` cookie.
            "access_token": self._access_token_for(user),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": serialize_user(user),
        }

    @staticmethod
    def _assert_session_current(payload: dict[str, Any], user: User) -> None:
        """Reject tokens issued before the last password change/deactivation.

        Tokens carry the `token_version` they were signed with; a reset bumps
        the column, which invalidates every refresh token issued earlier.
        """
        try:
            issued_version = int(payload.get("ver", 0))
        except (TypeError, ValueError):
            issued_version = -1
        if issued_version != (user.token_version or 0):
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Session has expired; sign in again",
            )

    @staticmethod
    def _invalid_refresh_message(token: str) -> str:
        """Point at the usual mistake: an access token sent to /auth/refresh."""
        try:
            claims = jwt.decode(
                token,
                settings.jwt_secret.get_secret_value(),
                algorithms=[JWT_ALGORITHM],
                options={"verify_exp": False},
            )
        except jwt.InvalidTokenError:
            return "Invalid refresh token"
        if claims.get("type") == "access":
            return (
                "That is an access token. POST /auth/refresh needs the refresh "
                f"token from the {settings.refresh_cookie_name} cookie set by "
                "/auth/login, not the access_token in its JSON body"
            )
        return "Invalid refresh token"

    @staticmethod
    def _issue_session(user: User) -> dict[str, Any]:
        return {
            "access_token": AuthService._access_token_for(user),
            "refresh_token": create_refresh_token(
                user_id=user.id,
                email=user.email,
                username=user.username,
                role=user.role,
                token_version=user.token_version or 0,
            ),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": serialize_user(user),
        }

    @staticmethod
    def _access_token_for(user: User) -> str:
        return create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
            token_version=user.token_version or 0,
        )

    async def record_refresh_failure(
        self,
        reason_code: str,
        context: RequestContext | None,
        *,
        user_id: int | None = None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_refresh_failure(
            scope=STAFF_SCOPE,
            reason_code=reason_code,
            context=context,
            actor_user_id=user_id,
        )

    async def record_logout(
        self,
        context: RequestContext | None = None,
        *,
        background: BackgroundTasks | None = None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_logout(
            scope=STAFF_SCOPE,
            context=context,
            background=background,
        )

    async def get_me(self, user_id: int) -> dict[str, Any]:
        user = await self.repository.get_by_id(user_id, include_deleted=True)
        if user is None or user.is_deleted:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                "User profile not found",
            )
        return serialize_user(user, snake_timestamps=True)
