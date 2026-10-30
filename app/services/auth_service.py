from __future__ import annotations

from typing import Any

import jwt
from fastapi import status

from app.core.config import settings
from app.core.errors import api_error
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


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def login(self, email: str, password: str) -> dict[str, Any]:
        user = await self.repository.get_by_email(email)
        if user is None:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid email or password",
            )

        if not verify_password(password, user.password_hash):
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid email or password",
            )

        if not user.is_active:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is deactivated. Please contact an administrator.",
            )

        return self._issue_session(user)

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        try:
            payload = decode_refresh_token(refresh_token)
        except jwt.ExpiredSignatureError as exc:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Refresh token has expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                self._invalid_refresh_message(refresh_token),
            ) from exc

        try:
            user_id = int(payload.get("id"))
        except (TypeError, ValueError) as exc:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "User account not found",
            ) from exc

        user = await self.repository.get_by_id(user_id, include_deleted=True)
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

        return {
            # Named explicitly: the refresh token is not in this body, it lives
            # in the httpOnly `diary_refresh_token` cookie.
            "access_token": self._access_token_for(user),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": serialize_user(user),
        }

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
