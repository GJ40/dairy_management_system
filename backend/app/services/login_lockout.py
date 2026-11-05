from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import status

from app.core.config import settings
from app.core.errors import api_error
from app.utils.time import utc_now_naive

LOCK_REASON_ATTEMPTS = "failed_login_attempts"
LOCK_REASON_ADMIN = "admin"


@dataclass(slots=True)
class FailureOutcome:
    """What one failed sign-in attempt did to the account's lockout state."""

    count: int
    cooldown_seconds: int = 0
    cooldown_started: bool = False
    locked: bool = False


def is_locked(account: object) -> bool:
    """True while the account is locked after failed sign-in attempts.

    Administrative deactivation is a separate state: it only flips
    ``is_active`` and does not set ``locked_at``, so it keeps the older 401
    "deactivated" response. A ``locked_at`` value marks the failed-attempt lock
    and requires an administrator to clear it.
    """
    return getattr(account, "locked_at", None) is not None


def format_duration(seconds: int) -> str:
    """Human-readable duration, e.g. 240 -> '4 minutes'."""
    total = max(0, int(seconds))
    minutes, remainder = divmod(total, 60)
    parts: list[str] = []
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if remainder or not parts:
        parts.append(f"{remainder} second{'s' if remainder != 1 else ''}")
    return " ".join(parts)


def cooldown_message(seconds: int) -> str:
    """User-facing cooldown text built from settings, never from constants.

    Changing LOGIN_COOLDOWN_MINUTES in `.env` changes every place this message
    is shown (login pages, API clients and logs) without a code change.
    """
    pause_minutes = settings.login_cooldown_minutes
    attempts = settings.login_cooldown_threshold
    return (
        "Too many failed sign-in attempts. "
        f"Sign-in is paused for {pause_minutes} minute"
        f"{'s' if pause_minutes != 1 else ''} after {attempts} failed "
        f"attempt{'s' if attempts != 1 else ''}. "
        f"Try again in {format_duration(seconds)}."
    )


def burst_expires_at(first_at: datetime, count: int) -> datetime:
    """End of the current failure burst.

    ``LOGIN_LOCKOUT_WINDOW_MINUTES`` measures a burst from its first failure.
    Once the burst reaches ``LOGIN_COOLDOWN_THRESHOLD`` the account is blocked
    for ``LOGIN_COOLDOWN_MINUTES``, and no attempt can be counted during that
    time. The window therefore grows by the cooldown, so the block does not
    consume the very evidence that produced it: without that, the cooldown
    would always expire after the window and the hard lock would be
    unreachable at the default thresholds. ``first_at`` is reset when the
    threshold is hit, so the pause always lasts the full configured duration.
    """
    window = timedelta(minutes=settings.login_lockout_window_minutes)
    if count >= settings.login_cooldown_threshold:
        window += timedelta(minutes=settings.login_cooldown_minutes)
    return first_at + window


def is_burst_expired(
    first_at: datetime | None,
    count: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True when the stored burst is too old to count towards a lockout."""
    if first_at is None:
        return True
    return (now or utc_now_naive()) > burst_expires_at(first_at, count)


def cooldown_remaining_seconds(
    account: object,
    *,
    now: datetime | None = None,
) -> int:
    """Seconds left in the temporary cooldown, or 0 when sign-in may proceed.

    The cooldown starts the moment a burst reaches ``LOGIN_COOLDOWN_THRESHOLD``
    (see :func:`register_failed_attempt`, which restarts ``first_at`` then) and
    lasts ``LOGIN_COOLDOWN_MINUTES``. It is derived from the stored burst, so no
    extra "cooldown until" column is needed: closing the browser tab, reloading
    or restarting the API cannot lose it.
    """
    first_at = getattr(account, "failed_login_first_at", None)
    count = int(getattr(account, "failed_login_count", 0) or 0)
    if first_at is None or count < settings.login_cooldown_threshold:
        return 0
    current = now or utc_now_naive()
    ends_at = first_at + timedelta(minutes=settings.login_cooldown_minutes)
    remaining = (ends_at - current).total_seconds()
    if remaining <= 0:
        return 0
    return int(math.ceil(remaining))


def register_failed_attempt(
    account: object,
    *,
    now: datetime | None = None,
) -> FailureOutcome:
    """Count one failed attempt, starting a cooldown or locking as configured.

    Mutates the ORM object only; the caller commits. The burst resets once the
    previous burst is past :func:`burst_expires_at`. On the attempt that reaches
    ``LOGIN_LOCKOUT_THRESHOLD`` the account is deactivated with an automatic
    lock reason and every existing session is revoked. That lock never expires:
    only an administrator can clear it.

    Callers must not call this while a cooldown is running: a blocked attempt
    is refused and recorded in the audit ledger, but it never advances the
    lockout counter.
    """
    current = now or utc_now_naive()
    first_at = getattr(account, "failed_login_first_at", None)
    count = int(getattr(account, "failed_login_count", 0) or 0)

    if is_burst_expired(first_at, count, now=current):
        first_at = current
        count = 0

    previous_count = count
    count += 1
    setattr(account, "failed_login_count", count)

    if count == settings.login_cooldown_threshold:
        # Start the pause when the threshold is reached, not at the first
        # failure: five guesses trickled across the window would otherwise
        # finish after a cooldown that had already expired, and no pause would
        # ever happen. The burst then restarts from this point.
        first_at = current
    setattr(account, "failed_login_first_at", first_at)

    outcome = FailureOutcome(count=count)

    if count >= settings.login_lockout_threshold:
        setattr(account, "is_active", False)
        setattr(account, "locked_at", current)
        setattr(account, "lock_reason", LOCK_REASON_ATTEMPTS)
        setattr(
            account,
            "token_version",
            (int(getattr(account, "token_version", 0) or 0)) + 1,
        )
        outcome.locked = True
        return outcome

    outcome.cooldown_seconds = cooldown_remaining_seconds(account, now=current)
    outcome.cooldown_started = (
        outcome.cooldown_seconds > 0
        and previous_count < settings.login_cooldown_threshold
    )
    return outcome


def cooldown_error(seconds: int) -> Exception:
    """429 used while an account's temporary cooldown is still running.

    The payload carries the remaining time and the configured pause length so
    the login page can render a countdown instead of parsing the message.
    """
    return api_error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "TOO_MANY_ATTEMPTS",
        cooldown_message(seconds),
        headers={"Retry-After": str(seconds)},
        extra={
            "retry_after_seconds": seconds,
            "cooldown_minutes": settings.login_cooldown_minutes,
            "cooldown_threshold": settings.login_cooldown_threshold,
        },
    )


def locked_error() -> Exception:
    """403 used once failed attempts have hard-locked the account."""
    attempts = settings.login_lockout_threshold
    return api_error(
        status.HTTP_403_FORBIDDEN,
        "ACCOUNT_LOCKED",
        f"Too many failed sign-in attempts. The account is locked after "
        f"{attempts} failed attempts and stays locked until an administrator "
        f"unlocks it.",
        extra={"lockout_threshold": attempts, "requires_admin_unlock": True},
    )


def reset_failed_attempts(account: object) -> None:
    """Clear the burst after a successful sign-in or an administrative unlock."""
    setattr(account, "failed_login_count", 0)
    setattr(account, "failed_login_first_at", None)


def clear_lock(account: object) -> None:
    """Remove the restriction and the failed-attempt burst."""
    setattr(account, "locked_at", None)
    setattr(account, "lock_reason", None)
    reset_failed_attempts(account)
