from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.core.errors import api_error
from app.core.security import hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    CreateUserRequest,
    UpdateUserRequest,
    UserQuery,
    serialize_user,
)
from app.utils.time import utc_now_iso


def parse_user_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"User with id {raw_id} not found",
        )
    return int(raw_id)


def _duplicate_message(exc: IntegrityError, *, creating: bool) -> str:
    text = str(getattr(exc, "orig", exc)).lower()
    if "email" in text:
        if creating:
            return "A user with this email address already exists"
        return "Email is already registered to another user"
    if "username" in text:
        if creating:
            return "A user with this username already exists"
        return "Username is already taken by another user"
    return "Duplicate entry conflict"


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def _commit(self, *, creating: bool) -> None:
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                _duplicate_message(exc, creating=creating),
            ) from exc

    async def list_users(self, query: UserQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_users(query)
        return {
            "items": [serialize_user(user) for user in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
        }

    async def get_user(self, raw_id: str) -> dict[str, Any]:
        user_id = parse_user_id(raw_id)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"User with id {raw_id} not found",
            )
        return serialize_user(user)

    async def create_user(self, payload: CreateUserRequest) -> dict[str, Any]:
        existing_email = await self.repository.get_by_email(payload.email)
        if existing_email is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                "A user with this email address already exists",
            )

        existing_username = await self.repository.get_by_username(payload.username)
        if existing_username is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_ENTRY",
                "A user with this username already exists",
            )

        user = await self.repository.create(
            full_name=payload.full_name,
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
        )
        await self._commit(creating=True)
        await self.repository.refresh(user)
        return serialize_user(user)

    async def update_user(
        self,
        raw_id: str,
        payload: UpdateUserRequest,
    ) -> dict[str, Any]:
        user_id = parse_user_id(raw_id)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"User with id {raw_id} not found",
            )

        updates = payload.model_dump(exclude_unset=True)

        if "full_name" in updates:
            user.full_name = updates["full_name"]

        if "username" in updates and updates["username"] != user.username:
            existing = await self.repository.get_by_username(
                updates["username"],
                exclude_id=user.id,
            )
            if existing is not None:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "DUPLICATE_ENTRY",
                    "Username is already taken by another user",
                )
            user.username = updates["username"]

        if "email" in updates and updates["email"] != user.email:
            existing = await self.repository.get_by_email(
                updates["email"],
                exclude_id=user.id,
            )
            if existing is not None:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "DUPLICATE_ENTRY",
                    "Email is already registered to another user",
                )
            user.email = updates["email"]

        if "password" in updates:
            user.password_hash = hash_password(updates["password"])
            # Administrative password change is a revocation event: sessions
            # issued with the old password must stop refreshing.
            user.token_version = (user.token_version or 0) + 1

        if "role" in updates:
            user.role = updates["role"]

        await self._commit(creating=False)
        await self.repository.refresh(user)
        return serialize_user(user)

    async def update_status(
        self,
        raw_id: str,
        is_active: bool,
        current_user_id: int,
    ) -> dict[str, Any]:
        user_id = parse_user_id(raw_id)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"User with id {raw_id} not found",
            )

        if user.id == current_user_id and not is_active:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "BAD_REQUEST",
                "Administrators cannot deactivate their own account",
            )

        if user.is_active != is_active:
            user.is_active = is_active
            # A token blocked only by is_active would work again after a
            # reactivation; bump so pre-deactivation sessions stay dead.
            user.token_version = (user.token_version or 0) + 1
        await self._commit(creating=False)
        await self.repository.refresh(user)
        return serialize_user(user)

    async def delete_user(
        self,
        raw_id: str,
        current_user_id: int,
    ) -> dict[str, Any]:
        """Soft-delete an operator account (admin-only, guarded by the router).

        Only operator accounts may be removed; admin accounts stay managed by
        deactivation, which is the behaviour the PRD defines. The row is kept
        so production, sales, wastage and expense history keeps its
        ``recorded_by`` reference.
        """
        user_id = parse_user_id(raw_id)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"User with id {raw_id} not found",
            )

        if user.id == current_user_id:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "BAD_REQUEST",
                "Administrators cannot delete their own account",
            )

        if user.role != "operator":
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "BAD_REQUEST",
                "Only operator accounts can be deleted; deactivate admin "
                "accounts instead",
            )

        user.is_deleted = True
        user.is_active = False
        user.token_version = (user.token_version or 0) + 1
        await self._commit(creating=False)

        return {
            "message": f"User #{user.id} deleted successfully",
            "resource": "users",
            "id": user.id,
            "deleted_at": utc_now_iso(),
        }
