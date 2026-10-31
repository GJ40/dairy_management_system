from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from starlette.background import BackgroundTasks

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.customer import Customer
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.password_reset_token import (
    RESET_SCOPE_CUSTOMER,
    RESET_SCOPE_STAFF,
    PasswordResetToken,
)
from app.models.user import User
from app.services.password_reset_service import (
    GENERIC_MESSAGE,
    PasswordResetService,
)
from app.utils.time import business_now_naive


class FakeResetRepository:
    """In-memory stand-in for PasswordResetRepository."""

    def __init__(self) -> None:
        self.records: list[PasswordResetToken] = []
        self._next_id = 1
        self.commits = 0

    async def create(
        self,
        *,
        scope: str,
        subject_id: int,
        token_hash: str,
        expires_at: Any,
    ) -> PasswordResetToken:
        record = PasswordResetToken(
            scope=scope,
            subject_id=subject_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        record.id = self._next_id
        self._next_id += 1
        self.records.append(record)
        return record

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return next((row for row in self.records if row.token_hash == token_hash), None)

    async def invalidate_outstanding(
        self,
        *,
        scope: str,
        subject_id: int,
        now: Any,
    ) -> None:
        for record in self.records:
            if (
                record.scope == scope
                and record.subject_id == subject_id
                and record.used_at is None
            ):
                record.used_at = now

    async def consume(self, token_id: int, *, now: Any) -> bool:
        for record in self.records:
            if record.id == token_id and record.used_at is None:
                record.used_at = now
                return True
        return False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self.users = users

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.users if user.email == email), None)

    async def get_by_id(self, user_id: int) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)


class FakeCustomerRepository:
    def __init__(self, customers: list[Customer]) -> None:
        self.customers = customers

    async def get_by_id(self, customer_id: int) -> Customer | None:
        return next((row for row in self.customers if row.id == customer_id), None)


class FakePortalAccountRepository:
    def __init__(self, accounts: list[CustomerPortalAccount]) -> None:
        self.accounts = accounts

    async def get_by_email(self, email: str) -> CustomerPortalAccount | None:
        return next((row for row in self.accounts if row.email == email), None)

    async def get_by_id(self, account_id: int) -> CustomerPortalAccount | None:
        return next((row for row in self.accounts if row.id == account_id), None)


class FakeEmailService:
    def __init__(self) -> None:
        self.resets: list[dict[str, Any]] = []
        self.changes: list[dict[str, Any]] = []

    async def send_password_reset(self, **kwargs: Any) -> bool:
        self.resets.append(kwargs)
        return True

    async def send_password_changed(self, **kwargs: Any) -> bool:
        self.changes.append(kwargs)
        return True


def make_staff() -> User:
    return User(
        id=1,
        full_name="Asha Patel",
        username="asha",
        email="asha@example.com",
        password_hash=hash_password("old-password"),
        role="operator",
        is_active=True,
        is_deleted=False,
    )


def make_customer() -> Customer:
    return Customer(
        id=3,
        name="Ravi Shah",
        rate_per_litre=Decimal("60.00"),
        is_active=True,
        is_deleted=False,
    )


def make_account(
    *,
    activated: bool = True,
    is_active: bool = True,
) -> CustomerPortalAccount:
    now = business_now_naive()
    return CustomerPortalAccount(
        id=7,
        customer_id=3,
        email="ravi@example.com",
        password_hash=hash_password("old-password") if activated else None,
        is_active=is_active,
        activated_at=now if activated else None,
        is_deleted=False,
    )


class PasswordResetServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.staff = make_staff()
        self.customer = make_customer()
        self.account = make_account()

        self.tokens = FakeResetRepository()
        self.users = FakeUserRepository([self.staff])
        self.accounts = FakePortalAccountRepository([self.account])
        self.customers = FakeCustomerRepository([self.customer])
        self.email = FakeEmailService()
        self.service = self._build_service()

    def _build_service(self) -> PasswordResetService:
        return PasswordResetService(
            repository=self.tokens,  # type: ignore[arg-type]
            user_repository=self.users,  # type: ignore[arg-type]
            account_repository=self.accounts,  # type: ignore[arg-type]
            customer_repository=self.customers,  # type: ignore[arg-type]
            email_service=self.email,  # type: ignore[arg-type]
        )

    def _token_from(self, url: str) -> str:
        return parse_qs(urlparse(url).query)["token"][0]

    def _only_token(self) -> str:
        self.assertEqual(len(self.email.resets), 1)
        return self._token_from(self.email.resets[0]["reset_url"])

    # --- requesting a link -------------------------------------------------

    async def test_unknown_staff_email_gets_generic_message_and_no_mail(self) -> None:
        result = await self.service.request_staff_reset("nobody@example.com")

        self.assertEqual(result, {"message": GENERIC_MESSAGE})
        self.assertEqual(self.email.resets, [])
        self.assertEqual(self.tokens.records, [])

    async def test_inactive_staff_account_gets_no_mail(self) -> None:
        self.staff.is_active = False

        result = await self.service.request_staff_reset(self.staff.email)

        self.assertEqual(result, {"message": GENERIC_MESSAGE})
        self.assertEqual(self.email.resets, [])

    async def test_staff_link_is_emailed_and_validates(self) -> None:
        await self.service.request_staff_reset(self.staff.email)

        url = self.email.resets[0]["reset_url"]
        self.assertTrue(url.startswith(f"{settings.frontend_base_url}/reset-password?"))
        self.assertEqual(self.email.resets[0]["to"], self.staff.email)
        self.assertEqual(await self.service.validate(RESET_SCOPE_STAFF, self._only_token()), {"valid": True})

    async def test_customer_link_uses_the_portal_reset_page(self) -> None:
        await self.service.request_customer_reset(self.account.email)

        url = self.email.resets[0]["reset_url"]
        self.assertTrue(
            url.startswith(f"{settings.frontend_base_url}/portal/reset-password?")
        )
        self.assertEqual(self.email.resets[0]["to"], self.account.email)

    async def test_unactivated_customer_account_gets_no_mail(self) -> None:
        self.account.password_hash = None
        self.account.activated_at = None

        result = await self.service.request_customer_reset(self.account.email)

        self.assertEqual(result, {"message": GENERIC_MESSAGE})
        self.assertEqual(self.email.resets, [])

    async def test_issuing_a_new_link_burns_the_previous_one(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        first = self._token_from(self.email.resets[0]["reset_url"])

        await self.service.request_staff_reset(self.staff.email)
        second = self._token_from(self.email.resets[1]["reset_url"])

        with self.assertRaises(HTTPException) as first_error:
            await self.service.validate(RESET_SCOPE_STAFF, first)
        self.assertEqual(first_error.exception.detail["code"], "RESET_TOKEN_USED")

        self.assertEqual(await self.service.validate(RESET_SCOPE_STAFF, second), {"valid": True})

    # --- token validation --------------------------------------------------

    async def test_unknown_token_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as error:
            await self.service.validate(RESET_SCOPE_STAFF, "not-a-real-token")

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(error.exception.detail["code"], "INVALID_RESET_TOKEN")

    async def test_expired_token_is_rejected(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()
        self.tokens.records[0].expires_at = business_now_naive() - timedelta(seconds=1)

        with self.assertRaises(HTTPException) as error:
            await self.service.validate(RESET_SCOPE_STAFF, token)

        self.assertEqual(error.exception.detail["code"], "RESET_TOKEN_EXPIRED")

    async def test_token_is_bound_to_its_scope(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()

        with self.assertRaises(HTTPException) as error:
            await self.service.validate(RESET_SCOPE_CUSTOMER, token)

        self.assertEqual(error.exception.detail["code"], "INVALID_RESET_TOKEN")

    # --- setting the new password -----------------------------------------

    async def test_reset_changes_the_password_and_emails_a_confirmation(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()

        result = await self.service.reset_password(
            RESET_SCOPE_STAFF, token, "brand-new-password"
        )

        self.assertIn("updated", result["message"])
        self.assertTrue(verify_password("brand-new-password", self.staff.password_hash))
        self.assertFalse(verify_password("old-password", self.staff.password_hash))
        # Bumping the version is what invalidates every earlier session.
        self.assertEqual(self.staff.token_version, 1)
        self.assertEqual(len(self.email.changes), 1)
        self.assertEqual(self.email.changes[0]["to"], self.staff.email)
        self.assertEqual(self.email.changes[0]["audience"], "staff")

    async def test_link_cannot_be_used_twice(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()
        await self.service.reset_password(RESET_SCOPE_STAFF, token, "brand-new-password")

        with self.assertRaises(HTTPException) as error:
            await self.service.reset_password(
                RESET_SCOPE_STAFF, token, "another-password"
            )

        self.assertEqual(error.exception.detail["code"], "RESET_TOKEN_USED")
        # The replay did not overwrite the password it was trying to replace.
        self.assertTrue(verify_password("brand-new-password", self.staff.password_hash))

    async def test_short_password_is_rejected_without_burning_the_token(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()

        with self.assertRaises(HTTPException) as error:
            await self.service.reset_password(RESET_SCOPE_STAFF, token, "short")

        self.assertEqual(error.exception.detail["code"], "WEAK_PASSWORD")
        self.assertIsNone(self.tokens.records[0].used_at)
        self.assertEqual(
            await self.service.validate(RESET_SCOPE_STAFF, token), {"valid": True}
        )

    async def test_customer_reset_updates_password_and_activation_state(self) -> None:
        await self.service.request_customer_reset(self.account.email)
        token = self._only_token()
        # A reset is also a valid way to finish activation, so the account is
        # flagged activated again if that timestamp ever went missing.
        self.account.activated_at = None

        await self.service.reset_password(
            RESET_SCOPE_CUSTOMER, token, "brand-new-password"
        )

        self.assertTrue(verify_password("brand-new-password", self.account.password_hash))
        self.assertIsNotNone(self.account.activated_at)
        self.assertEqual(self.account.token_version, 1)
        self.assertEqual(self.email.changes[0]["audience"], "customer portal")

    async def test_deactivated_customer_link_stops_working(self) -> None:
        await self.service.request_customer_reset(self.account.email)
        token = self._only_token()
        self.account.is_active = False

        with self.assertRaises(HTTPException) as error:
            await self.service.reset_password(
                RESET_SCOPE_CUSTOMER, token, "brand-new-password"
            )

        self.assertEqual(error.exception.detail["code"], "INVALID_RESET_TOKEN")
        self.assertFalse(verify_password("brand-new-password", self.account.password_hash or ""))

    async def test_reset_link_email_is_deferred_to_the_background(self) -> None:
        background = BackgroundTasks()

        await self.service.request_staff_reset(
            self.staff.email, background=background
        )

        # The response no longer waits on SMTP, so timing cannot reveal whether
        # the address has an account.
        self.assertEqual(self.email.resets, [])
        self.assertEqual(len(background.tasks), 1)

        await background()
        self.assertEqual(len(self.email.resets), 1)
        self.assertEqual(self.email.resets[0]["to"], self.staff.email)

    async def test_password_changed_email_is_deferred_to_the_background(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()
        background = BackgroundTasks()

        await self.service.reset_password(
            RESET_SCOPE_STAFF,
            token,
            "brand-new-password",
            background=background,
        )

        self.assertEqual(self.email.changes, [])
        await background()
        self.assertEqual(len(self.email.changes), 1)

    async def test_reset_records_tokens_hashed_not_in_plain_text(self) -> None:
        await self.service.request_staff_reset(self.staff.email)
        token = self._only_token()

        self.assertEqual(len(self.tokens.records), 1)
        self.assertNotEqual(self.tokens.records[0].token_hash, token)
        self.assertEqual(len(self.tokens.records[0].token_hash), 64)


if __name__ == "__main__":
    unittest.main()
