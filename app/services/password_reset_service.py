from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, status

from app.core.config import settings
from app.core.errors import api_error
from app.core.security import hash_password
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.password_reset_token import (
    RESET_SCOPE_CUSTOMER,
    RESET_SCOPE_STAFF,
    PasswordResetToken,
)
from app.models.user import User
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_repository import CustomerRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.schemas.customer_portal_auth import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH
from app.services.email_service import EmailService
from app.utils.tasks import deliver_or_queue
from app.utils.time import business_now_naive

# Deliberately identical for known and unknown addresses: the endpoint must not
# reveal whether an account exists.
GENERIC_MESSAGE = (
    "If an account exists for that email, we have sent a password reset link. "
    "Check your inbox and spam folder."
)
SUCCESS_MESSAGE = "Your password has been updated. Sign in with your new password."

_AUDIENCE = {
    RESET_SCOPE_STAFF: "staff",
    RESET_SCOPE_CUSTOMER: "customer portal",
}
_RESET_PATH = {
    RESET_SCOPE_STAFF: "/reset-password",
    RESET_SCOPE_CUSTOMER: "/portal/reset-password",
}


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_reset_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = business_now_naive() + timedelta(
        minutes=settings.password_reset_ttl_minutes
    )
    return token, hash_reset_token(token), expires_at


def _invalid_token() -> Exception:
    return api_error(
        status.HTTP_400_BAD_REQUEST,
        "INVALID_RESET_TOKEN",
        "This password reset link is invalid. Request a new one.",
    )


def _used_token() -> Exception:
    return api_error(
        status.HTTP_400_BAD_REQUEST,
        "RESET_TOKEN_USED",
        "This password reset link has already been used. Request a new one.",
    )


def _expired_token() -> Exception:
    return api_error(
        status.HTTP_400_BAD_REQUEST,
        "RESET_TOKEN_EXPIRED",
        "This password reset link has expired. Request a new one.",
    )


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


class PasswordResetService:
    def __init__(
        self,
        repository: PasswordResetRepository,
        user_repository: UserRepository,
        account_repository: CustomerPortalAccountRepository,
        customer_repository: CustomerRepository,
        email_service: EmailService,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository
        self.account_repository = account_repository
        self.customer_repository = customer_repository
        self.email_service = email_service

    async def request_staff_reset(
        self,
        email: str,
        *,
        background: BackgroundTasks | None = None,
    ) -> dict[str, str]:
        user = await self.user_repository.get_by_email(email)
        if user is not None and user.is_active:
            await self._send_reset_link(
                scope=RESET_SCOPE_STAFF,
                subject_id=user.id,
                email=user.email,
                name=user.full_name,
                background=background,
            )
        return {"message": GENERIC_MESSAGE}

    async def request_customer_reset(
        self,
        email: str,
        *,
        background: BackgroundTasks | None = None,
    ) -> dict[str, str]:
        account = await self.account_repository.get_by_email(email)
        if (
            account is not None
            and account.is_active
            and account.password_hash is not None
            and account.activated_at is not None
        ):
            customer = await self.customer_repository.get_by_id(account.customer_id)
            if customer is not None and customer.is_active:
                await self._send_reset_link(
                    scope=RESET_SCOPE_CUSTOMER,
                    subject_id=account.id,
                    email=account.email,
                    name=customer.name,
                    background=background,
                )
        return {"message": GENERIC_MESSAGE}

    async def validate(self, scope: str, token: str) -> dict[str, bool]:
        await self._require_valid(scope, token)
        return {"valid": True}

    async def reset_password(
        self,
        scope: str,
        token: str,
        password: str,
        *,
        background: BackgroundTasks | None = None,
    ) -> dict[str, str]:
        record = await self._require_valid(scope, token)
        _validate_new_password(password)

        subject = await self._get_subject(scope, record.subject_id)
        if subject is None:
            raise _invalid_token()

        now = business_now_naive()
        # Atomic: two concurrent submissions of the same link cannot both win.
        if not await self.repository.consume(record.id, now=now):
            raise _used_token()

        subject.password_hash = hash_password(password)
        # Every session issued before this reset must stop working, even one
        # holding a still-valid refresh token.
        subject.token_version = (subject.token_version or 0) + 1
        if isinstance(subject, CustomerPortalAccount):
            subject.activated_at = subject.activated_at or now
            subject.activation_token_hash = None
            subject.activation_expires_at = None

        await self.repository.invalidate_outstanding(
            scope=scope,
            subject_id=record.subject_id,
            now=now,
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await deliver_or_queue(
            background,
            self.email_service.send_password_changed,
            to=subject.email,
            name=await self._display_name(scope, subject),
            audience=_AUDIENCE[scope],
        )
        return {"message": SUCCESS_MESSAGE}

    async def _send_reset_link(
        self,
        *,
        scope: str,
        subject_id: int,
        email: str,
        name: str,
        background: BackgroundTasks | None = None,
    ) -> None:
        token, token_hash, expires_at = issue_reset_token()
        await self.repository.invalidate_outstanding(
            scope=scope,
            subject_id=subject_id,
            now=business_now_naive(),
        )
        await self.repository.create(
            scope=scope,
            subject_id=subject_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        reset_url = f"{settings.frontend_base_url}{_RESET_PATH[scope]}?token={token}"
        await deliver_or_queue(
            background,
            self.email_service.send_password_reset,
            to=email,
            name=name,
            reset_url=reset_url,
            audience=_AUDIENCE[scope],
        )

    async def _require_valid(
        self,
        scope: str,
        token: str,
    ) -> PasswordResetToken:
        if scope not in _RESET_PATH:
            raise _invalid_token()

        record = await self.repository.get_by_hash(hash_reset_token(token.strip()))
        if record is None or record.scope != scope:
            raise _invalid_token()
        if record.used_at is not None:
            raise _used_token()
        if record.expires_at <= business_now_naive():
            raise _expired_token()
        return record

    async def _get_subject(
        self,
        scope: str,
        subject_id: int,
    ) -> User | CustomerPortalAccount | None:
        if scope == RESET_SCOPE_STAFF:
            user = await self.user_repository.get_by_id(subject_id)
            if user is None or not user.is_active:
                return None
            return user

        account = await self.account_repository.get_by_id(subject_id)
        if account is None or not account.is_active:
            return None
        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            return None
        return account

    async def _display_name(
        self,
        scope: str,
        subject: User | CustomerPortalAccount,
    ) -> str:
        if isinstance(subject, User):
            return subject.full_name
        customer = await self.customer_repository.get_by_id(subject.customer_id)
        return customer.name if customer is not None else "there"

