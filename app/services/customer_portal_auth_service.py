from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import status

from app.core.config import settings
from app.core.errors import api_error
from app.core.security import (
    create_customer_access_token,
    create_customer_refresh_token,
    decode_customer_refresh_token,
    hash_password,
    verify_password,
)
from app.models.customer_portal_account import CustomerPortalAccount
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer_portal_auth import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    CreatePortalAccountRequest,
    PortalAccountQuery,
    serialize_account_event,
    serialize_activation,
    serialize_portal_account,
)
from app.utils.time import business_now_naive


def hash_activation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_activation_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = business_now_naive() + timedelta(
        hours=settings.customer_activation_ttl_hours
    )
    return token, hash_activation_token(token), expires_at


def _validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "WEAK_PASSWORD",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "WEAK_PASSWORD",
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes",
        )


def _invalid_login() -> Exception:
    return api_error(
        status.HTTP_401_UNAUTHORIZED,
        "UNAUTHORIZED",
        "Invalid email or password",
    )


class CustomerPortalAuthService:
    def __init__(
        self,
        repository: CustomerPortalAccountRepository,
        customer_repository: CustomerRepository,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository

    async def activate(self, token: str, password: str) -> dict[str, Any]:
        account = await self.repository.get_by_activation_hash(
            hash_activation_token(token)
        )
        if account is None:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_ACTIVATION_TOKEN",
                "Activation token is invalid or has already been used",
            )

        if account.password_hash is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ALREADY_ACTIVATED",
                "This portal account is already activated",
            )

        if (
            account.activation_expires_at is None
            or account.activation_expires_at <= business_now_naive()
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "ACTIVATION_TOKEN_EXPIRED",
                "Activation token has expired; ask the dairy to reissue it",
            )

        if not account.is_active:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_INACTIVE",
                "This portal account is deactivated",
            )

        _validate_new_password(password)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_INACTIVE",
                "The linked customer account is inactive",
            )

        account.password_hash = hash_password(password)
        account.activated_at = business_now_naive()
        account.activation_token_hash = None
        account.activation_expires_at = None
        await self.repository.add_event(
            account_id=account.id,
            action="activated",
            actor_user_id=None,
            note="Self-service activation",
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        return {
            "message": "Portal account activated. Sign in to continue.",
            "account": serialize_portal_account(account, customer),
        }

    async def login(self, email: str, password: str) -> dict[str, Any]:
        account = await self.repository.get_by_email(email)
        if account is None or not account.password_hash:
            raise _invalid_login()

        if not verify_password(password, account.password_hash):
            raise _invalid_login()

        if not account.is_active or account.activated_at is None:
            raise _invalid_login()

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise _invalid_login()

        account.last_login_at = business_now_naive()
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return {
            "access_token": self._access_token(account),
            "refresh_token": self._refresh_token(account),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "account": serialize_portal_account(account, customer),
        }

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        try:
            payload = decode_customer_refresh_token(refresh_token)
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
                "Invalid refresh token",
            ) from exc

        try:
            account_id = int(payload.get("account_id"))
            customer_id = int(payload.get("customer_id"))
        except (TypeError, ValueError) as exc:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account not found",
            ) from exc

        account = await self.repository.get_by_id(account_id, include_deleted=True)
        if (
            account is None
            or account.is_deleted
            or account.customer_id != customer_id
            or not account.is_active
            or account.activated_at is None
            or not account.password_hash
        ):
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is not available",
            )

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is not available",
            )

        return {
            "access_token": self._access_token(account),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "account": serialize_portal_account(account, customer),
        }

    async def get_me(self, account: CustomerPortalAccount) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {"account": serialize_portal_account(account, customer)}

    @staticmethod
    def _access_token(account: CustomerPortalAccount) -> str:
        return create_customer_access_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
        )

    @staticmethod
    def _refresh_token(account: CustomerPortalAccount) -> str:
        return create_customer_refresh_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
        )


class CustomerPortalAccountService:
    def __init__(
        self,
        repository: CustomerPortalAccountRepository,
        customer_repository: CustomerRepository,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository

    async def list_accounts(self, query: PortalAccountQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_and_count(query)
        items = []
        for account in rows:
            customer = await self.customer_repository.get_by_id(account.customer_id)
            items.append(serialize_portal_account(account, customer))
        return {
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def get_account(self, account_id: int) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        customer = await self.customer_repository.get_by_id(account.customer_id)
        events = await self.repository.list_events(account.id)
        return {
            "account": serialize_portal_account(account, customer),
            "events": [serialize_account_event(event) for event in events],
        }

    async def provision(
        self,
        payload: CreatePortalAccountRequest,
        actor_user_id: int,
    ) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(payload.customer_id)
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {payload.customer_id} not found",
            )
        if not customer.is_active:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "CUSTOMER_INACTIVE",
                "Cannot provision a portal account for an inactive customer",
            )

        if (
            await self.repository.get_by_customer_id(
                payload.customer_id, include_deleted=True
            )
            is not None
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ACCOUNT_EXISTS",
                "This customer already has a portal account",
            )

        if (
            await self.repository.get_by_email(payload.email, include_deleted=True)
            is not None
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "EMAIL_IN_USE",
                "That email is already used by another portal account",
            )

        token, token_hash, expires_at = issue_activation_token()
        account = await self.repository.create(
            customer_id=payload.customer_id,
            email=payload.email,
            activation_token_hash=token_hash,
            activation_expires_at=expires_at,
        )
        await self.repository.add_event(
            account_id=account.id,
            action="provisioned",
            actor_user_id=actor_user_id,
            note=None,
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def reactivate(
        self,
        account_id: int,
        actor_user_id: int,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        token, token_hash, expires_at = issue_activation_token()

        account.is_active = True
        account.password_hash = None
        account.activated_at = None
        account.activation_token_hash = token_hash
        account.activation_expires_at = expires_at
        await self.repository.add_event(
            account_id=account.id,
            action="reactivated",
            actor_user_id=actor_user_id,
            note="Fresh activation token issued; new password required",
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def deactivate(
        self,
        account_id: int,
        reason: str,
        actor_user_id: int,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        account.is_active = False
        account.activation_token_hash = None
        account.activation_expires_at = None
        await self.repository.add_event(
            account_id=account.id,
            action="deactivated",
            actor_user_id=actor_user_id,
            note=reason,
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {"account": serialize_portal_account(account, customer)}

    async def reset_activation(
        self,
        account_id: int,
        actor_user_id: int,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        if account.activated_at is not None or account.password_hash is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ALREADY_ACTIVATED",
                "This portal account is already activated",
            )

        token, token_hash, expires_at = issue_activation_token()
        account.activation_token_hash = token_hash
        account.activation_expires_at = expires_at
        await self.repository.add_event(
            account_id=account.id,
            action="password_reset",
            actor_user_id=actor_user_id,
            note="Activation token reissued",
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def _get_or_404(self, account_id: int) -> CustomerPortalAccount:
        account = await self.repository.get_by_id(account_id)
        if account is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Portal account with id {account_id} not found",
            )
        return account
