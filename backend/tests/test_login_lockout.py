from __future__ import annotations

import unittest
from datetime import timedelta

from fastapi import HTTPException

from app.core.config import settings
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.customer_portal_auth_service import CustomerPortalAuthService
from app.services.login_lockout import (
    LOCK_REASON_ATTEMPTS,
    clear_lock,
    cooldown_error,
    cooldown_remaining_seconds,
    is_locked,
    register_failed_attempt,
    reset_failed_attempts,
)
from app.services.user_service import UserService
from app.utils.time import utc_now_naive
from tests.test_auth_and_users import PASSWORD, FakeUserRepository, make_user
from tests.test_customer_portal_auth import (
    FakeCustomerRepository,
    FakePortalAccountRepository,
    make_account,
    make_customer,
)


class FakeLoginSecurity:
    """Captures the calls the login services make during an attempt."""

    def __init__(self) -> None:
        self.failures: list[dict[str, object]] = []
        self.locks: list[dict[str, object]] = []
        self.successes: list[dict[str, object]] = []

    async def record_failure(self, **kwargs: object) -> None:
        self.failures.append(kwargs)

    async def record_account_locked(self, **kwargs: object) -> None:
        self.locks.append(kwargs)

    async def record_success(self, **kwargs: object) -> None:
        self.successes.append(kwargs)


def fresh_user() -> User:
    user = make_user()
    user.failed_login_count = 0
    user.failed_login_first_at = None
    user.locked_at = None
    user.lock_reason = None
    user.token_version = 0
    return user


class LockoutStateTests(unittest.TestCase):
    def test_first_failure_starts_a_burst(self) -> None:
        user = fresh_user()
        outcome = register_failed_attempt(user)

        self.assertEqual(outcome.count, 1)
        self.assertFalse(outcome.locked)
        self.assertEqual(outcome.cooldown_seconds, 0)
        self.assertIsNotNone(user.failed_login_first_at)

    def test_cooldown_starts_at_the_configured_threshold(self) -> None:
        user = fresh_user()
        for _ in range(settings.login_cooldown_threshold - 1):
            outcome = register_failed_attempt(user)
        self.assertEqual(outcome.cooldown_seconds, 0)

        outcome = register_failed_attempt(user)

        self.assertTrue(outcome.cooldown_started)
        self.assertGreater(outcome.cooldown_seconds, 0)
        self.assertLessEqual(
            outcome.cooldown_seconds, settings.login_cooldown_minutes * 60
        )
        self.assertFalse(is_locked(user))

    def test_slow_burst_starts_a_full_cooldown_at_the_threshold(self) -> None:
        """Guesses trickled across the window must still trigger a pause.

        Measuring the cooldown from the first failure let five slow guesses
        finish with no pause at all, because the pause had already run out by
        the time the fifth attempt arrived.
        """
        user = fresh_user()
        now = utc_now_naive()
        user.failed_login_count = settings.login_cooldown_threshold - 1
        user.failed_login_first_at = now - timedelta(
            minutes=max(0, settings.login_lockout_window_minutes - 1)
        )

        outcome = register_failed_attempt(user, now=now)

        self.assertTrue(outcome.cooldown_started)
        self.assertAlmostEqual(
            outcome.cooldown_seconds,
            settings.login_cooldown_minutes * 60,
            delta=2,
        )
        self.assertEqual(user.failed_login_first_at, now)

    def test_cooldown_error_embeds_the_configured_values(self) -> None:
        """The 429 body carries the pause length from settings, not a literal."""
        error = cooldown_error(90)
        self.assertIsInstance(error, HTTPException)
        if not isinstance(error, HTTPException):  # pragma: no cover - typing guard
            self.fail("cooldown_error must raise an HTTPException")

        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.headers["Retry-After"], "90")
        self.assertEqual(error.detail["retry_after_seconds"], 90)
        self.assertEqual(
            error.detail["cooldown_minutes"], settings.login_cooldown_minutes
        )
        self.assertEqual(
            error.detail["cooldown_threshold"], settings.login_cooldown_threshold
        )
        self.assertIn(
            f"{settings.login_cooldown_minutes} minute", error.detail["message"]
        )
        self.assertIn("1 minute 30 seconds", error.detail["message"])

    def test_window_expiry_restarts_the_burst(self) -> None:
        user = fresh_user()
        user.failed_login_count = settings.login_cooldown_threshold - 1
        user.failed_login_first_at = utc_now_naive() - timedelta(
            minutes=settings.login_lockout_window_minutes + 1
        )

        outcome = register_failed_attempt(user)

        self.assertEqual(outcome.count, 1)
        self.assertFalse(outcome.locked)

    def test_cooldown_time_is_given_back_to_the_burst_window(self) -> None:
        """A burst that reached the cooldown keeps counting after the pause.

        Otherwise the pause would outlive the counting window, the burst would
        reset before anyone could fail again, and the hard lock would never be
        reachable.
        """
        user = fresh_user()
        user.failed_login_count = settings.login_cooldown_threshold
        user.failed_login_first_at = utc_now_naive() - timedelta(
            minutes=settings.login_lockout_window_minutes + 1
        )

        outcome = register_failed_attempt(user)

        self.assertEqual(outcome.count, settings.login_cooldown_threshold + 1)

    def test_burst_expires_after_the_window_and_the_cooldown(self) -> None:
        user = fresh_user()
        user.failed_login_count = settings.login_cooldown_threshold
        user.failed_login_first_at = utc_now_naive() - timedelta(
            minutes=(
                settings.login_lockout_window_minutes
                + settings.login_cooldown_minutes
                + 1
            )
        )

        outcome = register_failed_attempt(user)

        self.assertEqual(outcome.count, 1)

    def test_reaching_the_threshold_locks_and_revokes_sessions(self) -> None:
        """The 10th wrong password locks; there is no "one more attempt"."""
        user = fresh_user()
        user.token_version = 3
        now = utc_now_naive()

        for _ in range(settings.login_lockout_threshold - 1):
            register_failed_attempt(user, now=now)
        self.assertFalse(is_locked(user))

        outcome = register_failed_attempt(user, now=now)

        self.assertTrue(outcome.locked)
        self.assertFalse(user.is_active)
        self.assertEqual(user.lock_reason, LOCK_REASON_ATTEMPTS)
        self.assertIsNotNone(user.locked_at)
        self.assertEqual(user.token_version, 4)

    def test_cooldown_expires_independently_of_the_counter(self) -> None:
        user = fresh_user()
        now = utc_now_naive()
        for _ in range(settings.login_cooldown_threshold):
            register_failed_attempt(user, now=now)
        self.assertGreater(cooldown_remaining_seconds(user, now=now), 0)

        later = now + timedelta(minutes=settings.login_cooldown_minutes + 1)
        self.assertEqual(cooldown_remaining_seconds(user, now=later), 0)

    def test_reset_and_clear(self) -> None:
        user = fresh_user()
        for _ in range(settings.login_cooldown_threshold):
            register_failed_attempt(user)
        reset_failed_attempts(user)
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.failed_login_first_at)

        for _ in range(settings.login_lockout_threshold):
            register_failed_attempt(user)
        self.assertTrue(is_locked(user))
        clear_lock(user)
        self.assertFalse(is_locked(user))
        self.assertIsNone(user.lock_reason)
        self.assertEqual(user.failed_login_count, 0)


class StaffLoginLockoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user = fresh_user()
        self.repository = FakeUserRepository([self.user])
        self.security = FakeLoginSecurity()
        self.service = AuthService(self.repository, self.security)  # type: ignore[arg-type]

    async def test_cooldown_refuses_and_does_not_count_attempts(self) -> None:
        for _ in range(settings.login_cooldown_threshold):
            with self.assertRaises(HTTPException) as raised:
                await self.service.login(self.user.email, "wrong-password")
            self.assertEqual(raised.exception.status_code, 401)

        count_at_cooldown = self.user.failed_login_count
        first_at = self.user.failed_login_first_at
        self.assertEqual(count_at_cooldown, settings.login_cooldown_threshold)

        # Hammering during the cooldown is refused with Retry-After and leaves
        # the lockout state untouched, so it can never turn into a lock.
        for _ in range(settings.login_lockout_threshold * 2):
            with self.assertRaises(HTTPException) as blocked:
                await self.service.login(self.user.email, "wrong-password")
            self.assertEqual(blocked.exception.status_code, 429)
            self.assertEqual(blocked.exception.detail["code"], "TOO_MANY_ATTEMPTS")
            self.assertGreater(int(blocked.exception.headers["Retry-After"]), 0)

        self.assertEqual(self.user.failed_login_count, count_at_cooldown)
        self.assertEqual(self.user.failed_login_first_at, first_at)
        self.assertFalse(is_locked(self.user))
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.security.locks, [])

    async def test_cooldown_then_lock_then_admin_unlock(self) -> None:
        for _ in range(settings.login_cooldown_threshold):
            with self.assertRaises(HTTPException) as raised:
                await self.service.login(self.user.email, "wrong-password")
            self.assertEqual(raised.exception.status_code, 401)

        # Let the cooldown run out; the same burst is still in progress.
        self.user.failed_login_first_at = utc_now_naive() - timedelta(
            minutes=settings.login_cooldown_minutes + 1
        )

        statuses = []
        for _ in range(
            settings.login_lockout_threshold - settings.login_cooldown_threshold
        ):
            with self.assertRaises(HTTPException) as raised:
                await self.service.login(self.user.email, "wrong-password")
            statuses.append(raised.exception.status_code)

        self.assertEqual(statuses[:-1], [401] * (len(statuses) - 1))
        self.assertEqual(statuses[-1], 403)
        # 5 + 5 = the configured 10: the lock happens on the threshold attempt.
        self.assertEqual(self.user.failed_login_count, settings.login_lockout_threshold)
        self.assertEqual(len(self.security.locks), 1)
        self.assertTrue(is_locked(self.user))
        self.assertFalse(self.user.is_active)

        # The right password does not get in while locked.
        with self.assertRaises(HTTPException) as locked:
            await self.service.login(self.user.email, PASSWORD)
        self.assertEqual(locked.exception.status_code, 403)
        self.assertEqual(locked.exception.detail["code"], "ACCOUNT_LOCKED")

        # An administrator unlock clears the lock and the burst.
        admin = make_user(user_id=2, email="root@example.com", username="root")
        users = UserService(FakeUserRepository([admin, self.user]))  # type: ignore[arg-type]
        await users.update_status(str(self.user.id), True, admin.id)
        self.assertFalse(is_locked(self.user))
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.failed_login_count, 0)

        session = await self.service.login(self.user.email, PASSWORD)
        self.assertIn("access_token", session)

    async def test_success_resets_earlier_failures(self) -> None:
        for _ in range(2):
            with self.assertRaises(HTTPException):
                await self.service.login(self.user.email, "wrong-password")
        await self.service.login(self.user.email, PASSWORD)

        self.assertEqual(self.user.failed_login_count, 0)
        self.assertIsNone(self.user.failed_login_first_at)


class PortalLoginLockoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(password=PASSWORD, activated=True)
        self.account.failed_login_count = 0
        self.account.failed_login_first_at = None
        self.account.locked_at = None
        self.account.lock_reason = None
        self.account.token_version = 0
        self.accounts = FakePortalAccountRepository([self.account])
        self.customers = FakeCustomerRepository([self.customer])
        self.security = FakeLoginSecurity()
        self.service = CustomerPortalAuthService(
            self.accounts,  # type: ignore[arg-type]
            self.customers,  # type: ignore[arg-type]
            self.security,  # type: ignore[arg-type]
        )

    async def test_locks_on_reaching_the_threshold(self) -> None:
        for _ in range(settings.login_cooldown_threshold):
            with self.assertRaises(HTTPException) as raised:
                await self.service.login(self.account.email, "wrong-password")
            self.assertEqual(raised.exception.status_code, 401)

        count_at_cooldown = self.account.failed_login_count
        with self.assertRaises(HTTPException) as cooldown:
            await self.service.login(self.account.email, "wrong-password")
        self.assertEqual(cooldown.exception.status_code, 429)
        self.assertEqual(self.account.failed_login_count, count_at_cooldown)

        self.account.failed_login_first_at = utc_now_naive() - timedelta(
            minutes=settings.login_cooldown_minutes + 1
        )

        for _ in range(
            settings.login_lockout_threshold - settings.login_cooldown_threshold
        ):
            with self.assertRaises(HTTPException):
                await self.service.login(self.account.email, "wrong-password")

        self.assertTrue(is_locked(self.account))
        self.assertEqual(self.account.failed_login_count, settings.login_lockout_threshold)
        self.assertEqual(self.account.lock_reason, LOCK_REASON_ATTEMPTS)
        self.assertEqual(len(self.security.locks), 1)

        with self.assertRaises(HTTPException) as locked:
            await self.service.login(self.account.email, PASSWORD)
        self.assertEqual(locked.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
