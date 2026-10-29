from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.core.security import create_access_token, verify_password
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

        token = create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
        )
        return {"token": token, "user": serialize_user(user)}

    async def get_me(self, user_id: int) -> dict[str, Any]:
        user = await self.repository.get_by_id(user_id, include_deleted=True)
        if user is None or user.is_deleted:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                "User profile not found",
            )
        return serialize_user(user, snake_timestamps=True)
