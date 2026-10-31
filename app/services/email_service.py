from __future__ import annotations

import html as html_module
import logging
import smtplib

import anyio
import emails

from app.core.config import settings

logger = logging.getLogger(__name__)

# Mailpit (and MailHog) listen on 1025 without TLS or authentication by default.
MAILPIT_PLAIN_PORT = 1025
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

BRAND_NAME = "AmritDhara Dairy"
BRAND_TAGLINE = "Dairy Operations"
SUPPORT_LINE = "If you did not request this, you can safely ignore this email."


def _escape(value: str) -> str:
    return html_module.escape(value or "", quote=True)


def _layout(*, heading: str, body_html: str, footer_note: str) -> str:
    """Shared responsive shell: inline styles only, no external assets."""
    return f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="background:#064e3b;padding:28px 32px;">
                <p style="margin:0;color:#6ee7b7;font-size:11px;letter-spacing:2px;text-transform:uppercase;font-weight:700;">{BRAND_TAGLINE}</p>
                <p style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:800;">{BRAND_NAME}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:32px 32px 8px;">
                <h1 style="margin:0 0 12px;font-size:20px;line-height:1.3;color:#0f172a;">{_escape(heading)}</h1>
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:8px 32px 32px;">
                <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">{footer_note}</p>
              </td>
            </tr>
            <tr>
              <td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:18px 32px;">
                <p style="margin:0;font-size:11px;line-height:1.6;color:#94a3b8;">
                  {BRAND_NAME} &middot; Anand, Gujarat &middot; Asia/Kolkata<br />
                  This is an automated message; please do not reply to it.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _button(label: str, url: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
  <tr>
    <td style="border-radius:10px;background:#059669;">
      <a href="{_escape(url)}" style="display:inline-block;padding:13px 26px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;">{_escape(label)}</a>
    </td>
  </tr>
</table>
<p style="margin:0 0 8px;font-size:12px;line-height:1.6;color:#64748b;">
  If the button does not work, copy this link into your browser:
</p>
<p style="margin:0;font-size:12px;line-height:1.6;word-break:break-all;">
  <a href="{_escape(url)}" style="color:#047857;">{_escape(url)}</a>
</p>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:14px;line-height:1.65;color:#334155;">{text}</p>'


class EmailService:
    """Sends transactional mail through SMTP using the `emails` package.

    With `SMTP_HOST` unset (the local default) nothing is sent: the message is
    logged instead, so password-reset links stay testable without a mail server.
    A delivery failure is logged and swallowed — it must never turn a valid
    request into a 500.
    """

    async def send_password_reset(
        self,
        *,
        to: str,
        name: str,
        reset_url: str,
        audience: str,
    ) -> bool:
        minutes = settings.password_reset_ttl_minutes
        heading = "Reset your password"
        greeting = f"Hello {_escape(name or 'there')},"
        body = (
            _paragraph(greeting)
            + _paragraph(
                f"We received a request to reset the password for your {audience} "
                "account. Choose a new password using the link below."
            )
            + _button("Choose a new password", reset_url)
            + _paragraph(
                f"This link can be used once and expires in {minutes} minutes. "
                f"{SUPPORT_LINE}"
            )
        )
        return await self._deliver(
            to=to,
            subject="Reset your password — AmritDhara Dairy",
            html=_layout(
                heading=heading,
                body_html=body,
                footer_note=(
                    "Password reset links are single-use. If yours has expired, "
                    "request a new one from the sign-in page."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                f"We received a request to reset the password for your {audience} "
                f"account.\nOpen this link to choose a new password:\n{reset_url}\n\n"
                f"The link can be used once and expires in {minutes} minutes.\n"
                f"{SUPPORT_LINE}\n"
            ),
            link=reset_url,
        )

    async def send_password_changed(
        self,
        *,
        to: str,
        name: str,
        audience: str,
    ) -> bool:
        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                f"The password for your {audience} account was changed just now. "
                "You can sign in with the new password."
            )
            + _paragraph(
                "If you did not make this change, contact the dairy immediately "
                "and request a new password reset."
            )
        )
        return await self._deliver(
            to=to,
            subject="Your password was changed — AmritDhara Dairy",
            html=_layout(
                heading="Your password was changed",
                body_html=body,
                footer_note=SUPPORT_LINE,
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                f"The password for your {audience} account was changed just now.\n"
                "If you did not make this change, contact the dairy immediately.\n"
            ),
        )

    async def send_portal_activation(
        self,
        *,
        to: str,
        name: str,
        activation_url: str,
        expires_hours: int,
    ) -> bool:
        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                "Your dairy has created a customer portal account for you. Set "
                "your password to start ordering milk, viewing bills and raising "
                "support queries online."
            )
            + _button("Activate my portal account", activation_url)
            + _paragraph(
                f"This link can be used once and expires in {expires_hours} hours. "
                "If it expires, ask the dairy to send a fresh one."
            )
        )
        return await self._deliver(
            to=to,
            subject="Activate your customer portal account — AmritDhara Dairy",
            html=_layout(
                heading="Activate your customer portal",
                body_html=body,
                footer_note=(
                    "This activation link is single-use. Never share it with anyone."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "Your dairy has created a customer portal account for you.\n"
                f"Set your password here:\n{activation_url}\n\n"
                f"The link can be used once and expires in {expires_hours} hours.\n"
            ),
            link=activation_url,
        )

    async def _deliver(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        link: str | None = None,
    ) -> bool:
        if not settings.mail_enabled:
            logger.warning(
                "SMTP is not configured (SMTP_HOST is empty); %r for %s was not "
                "sent.%s",
                subject,
                to,
                f" Link: {link}" if link else "",
            )
            return False

        message = emails.html(
            html=html,
            text=text,
            subject=subject,
            mail_from=(settings.mail_from_name, settings.mail_from_email),
        )
        host = settings.smtp_host.strip()
        port = settings.smtp_port
        ssl = settings.smtp_use_ssl
        tls = settings.smtp_use_tls and not ssl
        user = settings.smtp_user.strip() or None
        password = settings.smtp_password.get_secret_value() or None

        # A local Mailpit uses a plain, unauthenticated listener; any TLS/auth
        # left over in .env would fail before a single message is sent.
        if (
            not settings.is_production
            and host.lower() in LOOPBACK_HOSTS
            and port == MAILPIT_PLAIN_PORT
            and (ssl or tls or user)
        ):
            logger.warning(
                "SMTP %s:%s is Mailpit's default plain listener; ignoring "
                "SMTP_USE_TLS/SMTP_USE_SSL/SMTP_USER/SMTP_PASSWORD for this send.",
                host,
                port,
            )
            ssl = tls = False
            user = password = None

        smtp_params = {
            "host": host,
            "port": port,
            "ssl": ssl,
            "tls": tls,
            "user": user,
            "password": password,
            "timeout": settings.smtp_timeout_seconds,
            "fail_silently": False,
        }
        logger.info(
            "Sending %r to %s via SMTP %s:%s (tls=%s, ssl=%s, auth=%s)",
            subject,
            to,
            host,
            port,
            tls,
            ssl,
            bool(user),
        )

        try:
            response = await anyio.to_thread.run_sync(
                lambda: message.send(to=to, smtp=smtp_params)
            )
        except Exception as exc:
            logger.exception("Could not send %r to %s", subject, to)
            logger.warning("%s", _smtp_failure_hint(host, port, exc))
            return False

        status_code = getattr(response, "status_code", None)
        if status_code not in (None, 250):
            logger.warning(
                "SMTP server returned status %s while sending %r to %s",
                status_code,
                subject,
                to,
            )
            return False
        return True


def _smtp_failure_hint(host: str, port: int, exc: Exception) -> str:
    """Actionable follow-up line for the most common local-SMTP mistakes."""
    detail = " ".join(
        part for part in (str(exc), getattr(exc, "strerror", "")) if part
    ).lower()
    is_dns = "getaddrinfo" in detail or "name or service not known" in detail
    is_local = host in LOOPBACK_HOSTS

    if is_dns:
        return (
            f"SMTP host {host!r} could not be resolved from this machine. "
            "Run Mailpit on the same host and use SMTP_HOST=127.0.0.1 "
            "(a Docker service name such as 'mailpit' only resolves inside "
            "that container network)."
        )
    if isinstance(exc, smtplib.SMTPNotSupportedError) or "starttls" in detail:
        return (
            f"SMTP {host}:{port} does not support STARTTLS. Mailpit's default "
            "listener has no TLS: set SMTP_USE_TLS=false (or SMTP_USE_SSL=false)."
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            f"SMTP {host}:{port} rejected the login. Mailpit needs no auth: "
            "leave SMTP_USER and SMTP_PASSWORD empty."
        )
    if is_local and port == MAILPIT_PLAIN_PORT:
        return (
            f"Could not reach Mailpit on {host}:{port}. Is Mailpit running? "
            "Its SMTP listener defaults to 1025 and the web UI to 8025."
        )
    return (
        f"Could not deliver mail via SMTP {host}:{port}. Check that the SMTP "
        "server is running and that SMTP_HOST, SMTP_PORT, SMTP_USER and "
        "SMTP_PASSWORD in backend_py/.env are correct."
    )
