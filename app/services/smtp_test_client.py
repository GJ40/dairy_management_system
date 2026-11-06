"""Admin-triggered SMTP probes: connection test and test-email delivery.

The probes only ever run against a candidate SMTP profile supplied by the
Admin settings API. Transactional email workflows never use this module.

Credentials are held in memory for the duration of one probe. This module
never logs, echoes or persists them; failures are reported as stable reason
codes with a fixed, secret-free message.
"""

from __future__ import annotations

import functools
import logging
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from typing import Callable

import anyio
import emails

logger = logging.getLogger(__name__)

DNS_FAILED = "DNS_FAILED"
CONNECT_FAILED = "CONNECT_FAILED"
TIMEOUT = "TIMEOUT"
TLS_FAILED = "TLS_FAILED"
TLS_NOT_SUPPORTED = "TLS_NOT_SUPPORTED"
AUTH_FAILED = "AUTH_FAILED"
SERVER_REJECTED = "SERVER_REJECTED"
UNKNOWN = "UNKNOWN"

REASON_MESSAGES = {
    DNS_FAILED: "The SMTP host could not be resolved.",
    CONNECT_FAILED: (
        "The SMTP server could not be reached on the configured host and port."
    ),
    TIMEOUT: "The SMTP server did not respond before the connection timeout.",
    TLS_FAILED: "The TLS handshake with the SMTP server failed.",
    TLS_NOT_SUPPORTED: "The SMTP server does not support the selected encryption mode.",
    AUTH_FAILED: "The SMTP server rejected the login.",
    SERVER_REJECTED: "The SMTP server rejected the test message.",
    UNKNOWN: "The SMTP test failed for an unknown reason.",
}

TEST_EMAIL_SUBJECT = "AmritDhara Dairy SMTP test message"

TEST_EMAIL_HTML = """\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
    <div style="max-width:520px;margin:32px auto;padding:28px 30px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;">
      <p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:#059669;">
        Email &amp; Notifications
      </p>
      <h1 style="margin:0 0 14px;font-size:20px;line-height:1.3;">SMTP test message</h1>
      <p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#334155;">
        This message confirms that the application can deliver email through the
        SMTP configuration selected in the administration settings.
      </p>
      <p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#334155;">
        No action is required. If you did not expect this message, an
        administrator sent a test from the dairy management system.
      </p>
      <p style="margin:0;padding-top:12px;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.6;color:#64748b;">
        AmritDhara Dairy &middot; automated test message
      </p>
    </div>
  </body>
</html>"""

TEST_EMAIL_TEXT = """\
SMTP TEST MESSAGE

This message confirms that the application can deliver email through the SMTP
configuration selected in the administration settings.

No action is required. If you did not expect this message, an administrator
sent a test from the dairy management system.

AmritDhara Dairy - automated test message
"""


class SmtpProbeError(Exception):
    """A safe, code-carrying SMTP probe failure."""

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(
            message or REASON_MESSAGES.get(reason_code, REASON_MESSAGES[UNKNOWN])
        )


@dataclass(frozen=True)
class SmtpProbeTarget:
    """One immutable SMTP candidate; credentials never appear in ``repr``."""

    host: str
    port: int
    auth_enabled: bool
    encryption_mode: str
    timeout_seconds: int
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)


def classify_smtp_exception(exc: BaseException) -> str:
    """Map a transport exception to a stable, non-sensitive reason code."""
    if isinstance(exc, SmtpProbeError):
        return exc.reason_code
    # Order matters: these are all ``OSError``/``SMTPException`` subclasses.
    if isinstance(exc, socket.gaierror):
        return DNS_FAILED
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return TIMEOUT
    if isinstance(exc, (ssl.SSLError, ssl.CertificateError)):
        return TLS_FAILED
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return TLS_NOT_SUPPORTED
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return AUTH_FAILED
    if isinstance(exc, smtplib.SMTPException):
        return SERVER_REJECTED
    if isinstance(exc, (ConnectionRefusedError, OSError)):
        return CONNECT_FAILED
    return UNKNOWN


def _tls_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def _open_client(target: SmtpProbeTarget) -> smtplib.SMTP:
    if target.encryption_mode == "ssl":
        return smtplib.SMTP_SSL(
            target.host,
            target.port,
            timeout=target.timeout_seconds,
            context=_tls_context(),
        )
    return smtplib.SMTP(
        target.host,
        target.port,
        timeout=target.timeout_seconds,
    )


def _probe_connection(target: SmtpProbeTarget) -> None:
    """Connect, negotiate encryption, authenticate and close. Sends no mail."""
    client: smtplib.SMTP | None = None
    try:
        client = _open_client(target)
        client.ehlo()
        if target.encryption_mode == "starttls":
            try:
                client.starttls(context=_tls_context())
            except smtplib.SMTPNotSupportedError as exc:
                raise SmtpProbeError(TLS_NOT_SUPPORTED) from exc
            client.ehlo()
        if target.auth_enabled:
            if not target.username or target.password is None:
                raise SmtpProbeError(
                    AUTH_FAILED,
                    "The SMTP profile is missing the credentials it needs.",
                )
            try:
                client.login(target.username, target.password)
            except smtplib.SMTPAuthenticationError as exc:
                raise SmtpProbeError(AUTH_FAILED) from exc
            except smtplib.SMTPNotSupportedError as exc:
                raise SmtpProbeError(
                    SERVER_REJECTED,
                    "The SMTP server does not offer SMTP authentication.",
                ) from exc
        client.noop()
    finally:
        if client is not None:
            # Closing must never mask the probe result.
            try:
                client.quit()
            except Exception:
                pass


def _deliver_test_email(
    target: SmtpProbeTarget,
    *,
    recipient: str,
    mail_from: tuple[str, str],
    subject: str,
    html: str,
    text: str,
) -> None:
    message = emails.html(html=html, text=text, subject=subject, mail_from=mail_from)
    smtp_params = {
        "host": target.host,
        "port": target.port,
        "ssl": target.encryption_mode == "ssl",
        "tls": target.encryption_mode == "starttls",
        "user": target.username if target.auth_enabled else None,
        "password": target.password if target.auth_enabled else None,
        "timeout": target.timeout_seconds,
        "fail_silently": False,
    }
    response = message.send(to=recipient, smtp=smtp_params)
    status_code = getattr(response, "status_code", None)
    if status_code not in (None, 250):
        raise SmtpProbeError(SERVER_REJECTED)


class SmtpTestClient:
    """Runs SMTP probes off the event loop and normalises their failures."""

    async def test_connection(self, target: SmtpProbeTarget) -> None:
        # ``run_sync`` passes no arguments, so the target must be bound here.
        await self._run(functools.partial(_probe_connection, target), target=target)

    async def send_test_email(
        self,
        target: SmtpProbeTarget,
        *,
        recipient: str,
        mail_from: tuple[str, str],
        subject: str = TEST_EMAIL_SUBJECT,
        html: str = TEST_EMAIL_HTML,
        text: str = TEST_EMAIL_TEXT,
    ) -> None:
        await self._run(
            functools.partial(
                _deliver_test_email,
                target,
                recipient=recipient,
                mail_from=mail_from,
                subject=subject,
                html=html,
                text=text,
            ),
            target=target,
        )

    @staticmethod
    async def _run(
        operation: Callable[[], None],
        *,
        target: SmtpProbeTarget,
    ) -> None:
        try:
            await anyio.to_thread.run_sync(operation)
        except SmtpProbeError:
            raise
        except Exception as exc:
            reason = classify_smtp_exception(exc)
            # Only the reason code and the endpoint are logged: exception text
            # can echo server responses that mention the account name.
            logger.warning(
                "SMTP probe to %s:%s failed (%s)",
                target.host,
                target.port,
                reason,
            )
            raise SmtpProbeError(reason) from None
