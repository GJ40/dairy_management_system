from __future__ import annotations

import html as html_module
import logging
import smtplib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import anyio
import emails

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from contextlib import AbstractAsyncContextManager

    from app.services.email_config_resolver import (
        EmailConfigResolver,
        EmailMessageConfig,
    )

    # A provider, not a resolver: the send may happen in a background task after
    # the request session is closed, so every resolution opens its own session.
    ResolverProvider = Callable[[], AbstractAsyncContextManager["EmailConfigResolver"]]

from app.core.config import settings
from app.services.email_config_resolver import EmailConfigurationError
from app.services.email_workflow_catalogue import category_of_event
from app.utils.time import business_timezone

logger = logging.getLogger(__name__)

# Mailpit (and MailHog) listen on 1025 without TLS or authentication by default.
MAILPIT_PLAIN_PORT = 1025
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

BRAND_NAME = "AmritDhara Dairy"
BRAND_TAGLINE = "Dairy Operations"
SUPPORT_LINE = "If you did not request this, you can safely ignore this email."


def _account_event_key(action: str, audience: str) -> str:
    """Catalogue key for one account email, chosen by its audience."""
    scope = "staff" if audience.strip().lower() == "staff" else "customer"
    return f"account.{scope}_{action}"


def _escape(value: str) -> str:
    return html_module.escape(value or "", quote=True)


# Semantic colours shared by the banner, callouts and detail tables.
_TONES = {
    "info": {
        "bg": "#eff6ff",
        "border": "#bfdbfe",
        "text": "#1e40af",
        "dot": "#2563eb",
    },
    "success": {
        "bg": "#ecfdf5",
        "border": "#a7f3d0",
        "text": "#065f46",
        "dot": "#059669",
    },
    "warning": {
        "bg": "#fffbeb",
        "border": "#fde68a",
        "text": "#92400e",
        "dot": "#d97706",
    },
    "danger": {
        "bg": "#fff1f2",
        "border": "#fecdd3",
        "text": "#9f1239",
        "dot": "#e11d48",
    },
}


def _layout(
    *,
    heading: str,
    body_html: str,
    footer_note: str,
    preheader: str = "",
    status_label: str | None = None,
    tone: str = "info",
    footer_disclaimer: str = "Automated security message",
) -> str:
    """Shared responsive shell: inline styles only, no external assets.

    ``preheader`` is the preview line mail clients show next to the subject;
    hiding it here keeps the inbox tidy without leaking it into the body.
    """
    palette = _TONES.get(tone, _TONES["info"])
    accent = palette["dot"]
    status_html = (
        f'<span style="display:inline-block;padding:5px 12px;border-radius:999px;'
        f'background:{palette["bg"]};color:{palette["text"]};font-size:10px;'
        f'font-weight:800;letter-spacing:1px;text-transform:uppercase;">'
        f"{_escape(status_label)}</span>"
        if status_label
        else ""
    )
    return f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">{_escape(preheader)}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="background:#064e3b;padding:24px 32px;border-bottom:3px solid {accent};">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="vertical-align:middle;">
                      <p style="margin:0;color:#6ee7b7;font-size:11px;letter-spacing:2px;text-transform:uppercase;font-weight:700;">{BRAND_TAGLINE}</p>
                      <p style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:-0.2px;">{BRAND_NAME}</p>
                    </td>
                    <td align="right" style="vertical-align:middle;padding-left:12px;">{status_html}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:32px 32px 8px;">
                <h1 style="margin:0 0 6px;font-size:22px;line-height:1.3;letter-spacing:-0.3px;color:#0f172a;">{_escape(heading)}</h1>
                <div style="width:44px;height:3px;border-radius:2px;background:{accent};margin:0 0 20px;"></div>
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
                <p style="margin:0 0 4px;font-size:11px;line-height:1.6;color:#94a3b8;">
                  {BRAND_NAME} &middot; Anand, Gujarat &middot; Asia/Kolkata
                </p>
                <p style="margin:0;font-size:11px;line-height:1.6;color:#94a3b8;">
                  {_escape(footer_disclaimer)} &middot; {_escape(settings.mail_from_email)} &middot; please do not reply
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
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 22px;">
  <tr>
    <td style="border-radius:10px;background:#059669;">
      <a href="{_escape(url)}" style="display:inline-block;padding:13px 26px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;">{_escape(label)}</a>
    </td>
  </tr>
</table>
<p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#94a3b8;">
  Or paste this link into your browser
</p>
<p style="margin:0 0 20px;font-size:12px;line-height:1.6;word-break:break-all;">
  <a href="{_escape(url)}" style="color:#047857;">{_escape(url)}</a>
</p>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:14px;line-height:1.65;color:#334155;">{text}</p>'


def _callout(title: str, text: str, *, tone: str = "warning") -> str:
    palette = _TONES.get(tone, _TONES["warning"])
    border = palette["border"]
    background = palette["bg"]
    colour = palette["text"]
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:2px 0 20px;border:1px solid {border};background:{background};border-radius:10px;">
  <tr>
    <td style="padding:14px 16px;">
      <p style="margin:0 0 4px;font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:{colour};">{_escape(title)}</p>
      <p style="margin:0;font-size:13px;line-height:1.6;color:{colour};">{text}</p>
    </td>
  </tr>
</table>"""


def _details_table(rows: list[tuple[str, str]]) -> str:
    """Two-column fact table; values may contain pre-escaped inline markup."""
    cells = "".join(
        "<tr>"
        f'<td style="padding:10px 14px;border-top:1px solid #eef2f7;width:40%;font-size:10px;'
        f'font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;'
        f'vertical-align:top;">{_escape(label)}</td>'
        f'<td style="padding:10px 14px;border-top:1px solid #eef2f7;font-size:13px;'
        f'line-height:1.5;color:#0f172a;">{value}</td>'
        "</tr>"
        for label, value in rows
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:2px 0 20px;border:1px solid #e2e8f0;border-radius:10px;'
        'border-collapse:separate;border-spacing:0;overflow:hidden;background:#ffffff;">'
        f"{cells}</table>"
    )


def _steps(items: list[str]) -> str:
    rows = "".join(
        "<tr>"
        '<td style="padding:0 0 10px;vertical-align:top;width:26px;">'
        f'<span style="display:inline-block;width:22px;height:22px;border-radius:999px;'
        f'background:#ecfdf5;color:#047857;font-size:11px;font-weight:800;'
        f'text-align:center;line-height:22px;">{index}</span></td>'
        f'<td style="padding:1px 0 10px 10px;font-size:13px;line-height:1.6;color:#334155;">'
        f"{text}</td></tr>"
        for index, text in enumerate(items, start=1)
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:2px 0 12px;">{rows}</table>'
    )


def _section_label(text: str) -> str:
    return (
        '<p style="margin:0 0 8px;font-size:10px;font-weight:800;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:#94a3b8;">{_escape(text)}</p>'
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _timestamp_pair(moment: datetime | None = None) -> tuple[str, str]:
    """(IST, UTC) display strings for one instant, defaulting to now."""
    utc_value = _as_utc(moment or datetime.now(timezone.utc))
    ist_value = utc_value.astimezone(business_timezone())
    return (
        ist_value.strftime("%d %b %Y, %H:%M:%S IST"),
        utc_value.strftime("%d %b %Y, %H:%M:%S UTC"),
    )


class EmailService:
    """Sends transactional mail through SMTP using the `emails` package.

    With `SMTP_HOST` unset (the local default) nothing is sent: the message is
    logged instead, so password-reset links stay testable without a mail server.
    A delivery failure is logged and swallowed — it must never turn a valid
    request into a 500.

    ``resolver_provider`` is optional on purpose. With one (see
    ``get_email_service``) the account, security and portal emails read their
    transport, From and Reply-To from the workflow mappings, exactly like the
    order notifications do. Without one, ``EmailService()`` keeps the
    environment behaviour that every direct caller and test relies on.
    """

    def __init__(self, resolver_provider: "ResolverProvider | None" = None) -> None:
        self.resolver_provider = resolver_provider

    async def send_password_reset(
        self,
        *,
        to: str,
        name: str,
        reset_url: str,
        audience: str,
    ) -> bool:
        minutes = settings.password_reset_ttl_minutes
        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                "We received a request to reset the password for your "
                f"<strong>{_escape(audience)}</strong> account. Use the button "
                "below to choose a new one."
            )
            + _button("Choose a new password", reset_url)
            + _section_label("What happens next")
            + _steps(
                [
                    "Open the link above and choose a new password.",
                    "Use at least 8 characters, and avoid a password you use "
                    "elsewhere.",
                    "Sign in with the new password. The link cannot be reused.",
                ]
            )
            + _details_table(
                [
                    ("Account", _escape(audience)),
                    ("Link expires", f"In {minutes} minutes"),
                    ("Valid for", "One sign-in change only"),
                ]
            )
            + _callout(
                "Did not request this?",
                "You can ignore this email - your current password stays "
                "unchanged and the link expires on its own.",
                tone="warning",
            )
        )
        return await self._deliver(
            event_key=_account_event_key("password_reset", audience),
            to=to,
            subject="Reset your password — AmritDhara Dairy",
            html=_layout(
                heading="Reset your password",
                body_html=body,
                preheader=(
                    f"Choose a new {audience} password. The link expires in "
                    f"{minutes} minutes."
                ),
                status_label="Action required",
                tone="warning",
                footer_note=(
                    "Password reset links are single-use. If yours has expired, "
                    "request a new one from the sign-in page."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "RESET YOUR PASSWORD\n\n"
                f"We received a request to reset the password for your "
                f"{audience} account.\n\n"
                f"Choose a new password:\n{reset_url}\n\n"
                "What happens next\n"
                "  1. Open the link and choose a new password.\n"
                "  2. Use at least 8 characters, and avoid a password you use "
                "elsewhere.\n"
                "  3. Sign in with the new password. The link cannot be reused.\n\n"
                f"Account: {audience}\n"
                f"Link expires: in {minutes} minutes\n"
                "Valid for: one password change only\n\n"
                "Did not request this? You can ignore this email - your "
                "current password stays unchanged.\n\n"
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
        changed_at = _timestamp_pair()
        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                "The password for your "
                f"<strong>{_escape(audience)}</strong> account was changed just "
                "now. You can sign in with the new password."
            )
            + _details_table(
                [
                    ("Account", _escape(audience)),
                    ("Changed at (IST)", _escape(changed_at[0])),
                    ("Changed at (UTC)", _escape(changed_at[1])),
                ]
            )
            + _callout(
                "Was this not you?",
                "Reset the password again immediately and tell the dairy so the "
                "account can be secured.",
                tone="danger",
            )
            + _paragraph(SUPPORT_LINE)
        )
        return await self._deliver(
            event_key=_account_event_key("password_changed", audience),
            to=to,
            subject="Your password was changed — AmritDhara Dairy",
            html=_layout(
                heading="Your password was changed",
                body_html=body,
                preheader=(
                    f"The password for your {audience} account was just changed."
                ),
                status_label="Password changed",
                tone="success",
                footer_note=SUPPORT_LINE,
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "YOUR PASSWORD WAS CHANGED\n\n"
                f"The password for your {audience} account was changed just now.\n"
                "You can sign in with the new password.\n\n"
                f"Account: {audience}\n"
                f"Changed at (IST): {changed_at[0]}\n"
                f"Changed at (UTC): {changed_at[1]}\n\n"
                "Was this not you? Reset the password again immediately and "
                "tell the dairy so the account can be secured.\n\n"
                f"{SUPPORT_LINE}\n"
            ),
        )

    async def send_failed_login_alert(
        self,
        *,
        to: str,
        name: str,
        scope: str,
        failure_count: int,
        window_minutes: int,
        occurred_at_utc: datetime,
        ip_address: str | None,
        user_agent: str | None,
        cooldown_minutes: int | None = None,
    ) -> bool:
        scope_label = "staff" if scope == "staff" else "customer portal"
        ist_text, utc_text = _timestamp_pair(occurred_at_utc)
        ip_text = ip_address or "Unknown"
        device_text = user_agent or "Unknown"

        cooldown_html = ""
        cooldown_text = ""
        if cooldown_minutes:
            cooldown_html = _callout(
                f"Sign-in paused for {cooldown_minutes} minutes",
                "Too many failed attempts were recorded, so sign-in to this "
                f"account is paused until the {cooldown_minutes}-minute cooling "
                "period ends. You can reset your password now, or try again "
                "once the countdown finishes.",
                tone="warning",
            )
            cooldown_text = (
                f"SIGN-IN PAUSED FOR {cooldown_minutes} MINUTES\n"
                "Too many failed attempts were recorded, so sign-in to this "
                "account is paused until the cooling period ends. You can reset "
                "your password now, or try again once the countdown finishes.\n\n"
            )

        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                f"We recorded <strong>{failure_count} failed sign-in "
                f"attempt{'s' if failure_count != 1 else ''}</strong> to your "
                f"{_escape(scope_label)} account in the last {window_minutes} "
                "minutes."
            )
            + cooldown_html
            + _section_label("Attempt details")
            + _details_table(
                [
                    ("Account type", _escape(scope_label)),
                    ("Failed attempts", f"<strong>{failure_count}</strong>"),
                    ("Alert window", f"Last {window_minutes} minutes"),
                    ("Detected (IST)", _escape(ist_text)),
                    ("Detected (UTC)", _escape(utc_text)),
                    ("IP address", _escape(ip_text)),
                    ("Device", _escape(device_text)),
                ]
            )
            + _section_label("What to do")
            + _steps(
                [
                    "If these attempts were yours, no action is needed.",
                    "If not, reset your password from the sign-in page right away.",
                    "Still unsure? Contact the dairy and quote the detection time "
                    "above.",
                ]
            )
        )
        return await self._deliver(
            event_key=_account_event_key("failed_login_alert", scope),
            to=to,
            subject="Security alert: failed sign-in attempts — AmritDhara Dairy",
            html=_layout(
                heading="Failed sign-in attempts on your account",
                body_html=body,
                preheader=(
                    f"{failure_count} failed sign-in attempts to your "
                    f"{scope_label} account in the last {window_minutes} minutes."
                ),
                status_label="Security alert",
                tone="warning",
                footer_note=(
                    "This alert never asks for your password or a verification "
                    "code. Sign in only through the dairy's usual address."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "SECURITY ALERT: FAILED SIGN-IN ATTEMPTS\n\n"
                f"We recorded {failure_count} failed sign-in attempt"
                f"{'s' if failure_count != 1 else ''} to your {scope_label} "
                f"account in the last {window_minutes} minutes.\n\n"
                f"{cooldown_text}"
                "Attempt details\n"
                f"  Account type:   {scope_label}\n"
                f"  Failed attempts: {failure_count}\n"
                f"  Alert window:   last {window_minutes} minutes\n"
                f"  Detected (IST): {ist_text}\n"
                f"  Detected (UTC): {utc_text}\n"
                f"  IP address:     {ip_text}\n"
                f"  Device:         {device_text}\n\n"
                "What to do\n"
                "  1. If these attempts were yours, no action is needed.\n"
                "  2. If not, reset your password from the sign-in page right "
                "away.\n"
                "  3. Still unsure? Contact the dairy and quote the detection "
                "time above.\n"
            ),
        )

    async def send_account_locked_notice(
        self,
        *,
        to: str,
        name: str,
        scope: str,
        failure_count: int,
        window_minutes: int,
        locked_at_utc: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> bool:
        scope_label = "staff" if scope == "staff" else "customer portal"
        ist_text, utc_text = _timestamp_pair(locked_at_utc)
        ip_text = ip_address or "Unknown"
        device_text = user_agent or "Unknown"

        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                f"Your <strong>{_escape(scope_label)}</strong> account has been "
                "locked after "
                f"<strong>{failure_count} failed sign-in "
                f"attempt{'s' if failure_count != 1 else ''}</strong> in the last "
                f"{window_minutes} minutes."
            )
            + _callout(
                "Sign-in is disabled",
                "The account stays locked until an administrator unlocks it. "
                "Contact the dairy with the time below and ask for an unlock.",
                tone="danger",
            )
            + _section_label("Lock details")
            + _details_table(
                [
                    ("Account type", _escape(scope_label)),
                    ("Failed attempts", f"<strong>{failure_count}</strong>"),
                    ("Alert window", f"Last {window_minutes} minutes"),
                    ("Locked at (IST)", _escape(ist_text)),
                    ("Locked at (UTC)", _escape(utc_text)),
                    ("IP address", _escape(ip_text)),
                    ("Device", _escape(device_text)),
                ]
            )
            + _section_label("What to do")
            + _steps(
                [
                    "Ask an administrator to unlock the account.",
                    "Change your password once the account is unlocked, before "
                    "signing in again.",
                    "If you did not attempt these sign-ins, tell the dairy so the "
                    "device and IP above can be reviewed.",
                ]
            )
        )
        return await self._deliver(
            event_key=_account_event_key("account_locked", scope),
            to=to,
            subject="Security alert: account locked — AmritDhara Dairy",
            html=_layout(
                heading="Your account has been locked",
                body_html=body,
                preheader=(
                    f"Your {scope_label} account was locked after "
                    f"{failure_count} failed sign-in attempts."
                ),
                status_label="Account locked",
                tone="danger",
                footer_note=(
                    "This alert never asks for your password or a verification "
                    "code. Sign in only through the dairy's usual address."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "ACCOUNT LOCKED\n\n"
                f"Your {scope_label} account has been locked after {failure_count} "
                f"failed sign-in attempt{'s' if failure_count != 1 else ''} in the "
                f"last {window_minutes} minutes.\n\n"
                "SIGN-IN IS DISABLED\n"
                "The account stays locked until an administrator unlocks it. "
                "Contact the dairy with the time below and ask for an unlock.\n\n"
                "Lock details\n"
                f"  Account type:    {scope_label}\n"
                f"  Failed attempts: {failure_count}\n"
                f"  Alert window:    last {window_minutes} minutes\n"
                f"  Locked at (IST): {ist_text}\n"
                f"  Locked at (UTC): {utc_text}\n"
                f"  IP address:      {ip_text}\n"
                f"  Device:          {device_text}\n\n"
                "What to do\n"
                "  1. Ask an administrator to unlock the account.\n"
                "  2. Change your password once the account is unlocked.\n"
                "  3. If you did not attempt these sign-ins, tell the dairy.\n"
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
            + _section_label("How to get started")
            + _steps(
                [
                    "Open the activation link above and choose a password.",
                    "Sign in to the portal with the email address the dairy "
                    "registered for you.",
                    "Review your deliveries, bills and payments in one place.",
                ]
            )
            + _details_table(
                [
                    ("Portal", "Customer self-service"),
                    ("Link expires", f"In {expires_hours} hours"),
                    ("Valid for", "One activation only"),
                ]
            )
            + _callout(
                "Keep this link private",
                "Anyone with this link can set your portal password. If it "
                "expires, ask the dairy to send a fresh invitation.",
                tone="info",
            )
        )
        return await self._deliver(
            event_key="portal.customer_activation",
            to=to,
            subject="Activate your customer portal account — AmritDhara Dairy",
            html=_layout(
                heading="Activate your customer portal",
                body_html=body,
                preheader=(
                    f"Set your portal password - this invitation expires in "
                    f"{expires_hours} hours."
                ),
                status_label="Invitation",
                tone="success",
                footer_note=(
                    "This activation link is single-use. Never share it with anyone."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "ACTIVATE YOUR CUSTOMER PORTAL\n\n"
                "Your dairy has created a customer portal account for you.\n\n"
                f"Set your password here:\n{activation_url}\n\n"
                "How to get started\n"
                "  1. Open the activation link and choose a password.\n"
                "  2. Sign in with the email address the dairy registered for "
                "you.\n"
                "  3. Review your deliveries, bills and payments in one place.\n\n"
                "Portal: customer self-service\n"
                f"Link expires: in {expires_hours} hours\n"
                "Valid for: one activation only\n\n"
                "Keep this link private - anyone with it can set your password.\n"
            ),
            link=activation_url,
        )

    async def send_support_query_answered(
        self,
        *,
        to: str,
        name: str,
        query_no: str,
        subject: str,
        portal_url: str,
    ) -> bool:
        """Tell a customer that the dairy replied to their support query.

        Deliberately carries no message body: the reply may contain details the
        dairy does not want sitting in an inbox indefinitely, so the email only
        points at the portal.
        """
        body = (
            _paragraph(f"Hello {_escape(name or 'there')},")
            + _paragraph(
                "The dairy has replied to your support query. Open the "
                "customer portal to read the answer and continue the "
                "conversation there."
            )
            + _section_label("Your query")
            + _details_table(
                [
                    ("Query number", f"<strong>{_escape(query_no)}</strong>"),
                    ("Subject", _escape(subject or "Support query")),
                    ("Status", "Answered"),
                ]
            )
            + _button("Open my queries", portal_url)
            + _steps(
                [
                    "Sign in to the customer portal and open Support.",
                    "Read the reply and add a message if you need more help.",
                    "A closed query can still be read, but no new messages "
                    "can be added to it.",
                ]
            )
            + _callout(
                "Why no reply in this email?",
                "The answer stays in the portal so the whole conversation "
                "stays together - this email only lets you know it is there.",
                tone="info",
            )
        )
        return await self._deliver(
            event_key="support.query_answered",
            to=to,
            subject=f"We replied to your query · {query_no} — AmritDhara Dairy",
            html=_layout(
                heading="Your query has been answered",
                body_html=body,
                preheader=f"The dairy replied to query {query_no}.",
                status_label="Answered",
                tone="success",
                footer_note=(
                    "You are receiving this because you raised a support "
                    "query in the customer portal."
                ),
            ),
            text=(
                f"Hello {name or 'there'},\n\n"
                "YOUR QUERY HAS BEEN ANSWERED\n\n"
                "The dairy has replied to your support query. Open the "
                "customer portal to read the answer.\n\n"
                f"  Query number: {query_no}\n"
                f"  Subject:      {subject or 'Support query'}\n"
                "  Status:       Answered\n\n"
                f"Open your queries:\n{portal_url}\n\n"
                "The reply is kept in the portal so the whole conversation "
                "stays together.\n\n"
                f"{SUPPORT_LINE}\n"
            ),
            link=portal_url,
        )

    async def _deliver_with_resolver(
        self,
        event_key: str,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        link: str | None = None,
    ) -> bool:
        """Deliver through the resolver; never raises, like the environment path."""
        assert self.resolver_provider is not None
        try:
            async with self.resolver_provider() as resolver:
                config = await resolver.resolve(
                    event_key,
                    category_key=category_of_event(event_key),
                )
        except EmailConfigurationError as exc:
            # Same local convenience as the environment path: the link is a live
            # credential and is only echoed outside production.
            link_note = f" Link: {link}" if link and not settings.is_production else ""
            logger.warning(
                "%r for %s was not sent: %s (%s).%s",
                subject,
                to,
                exc,
                exc.code,
                link_note,
            )
            return False
        except Exception:
            logger.exception(
                "Resolving the sender for %r to %s failed", subject, to
            )
            return False

        return await self.send_with_config(
            config,
            to=to,
            subject=subject,
            html=html,
            text=text,
        )

    async def send_with_config(
        self,
        config: "EmailMessageConfig",
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> bool:
        """Send one message through an already-resolved configuration.

        ``EmailConfigResolver`` decides the transport, From and Reply-To per
        send, so this path never reads SMTP settings from the environment on its
        own. A delivery failure is logged and swallowed, exactly like
        ``_deliver``: mail must never turn a valid request into a 500.
        """
        if config.source == "environment" and not settings.mail_enabled:
            logger.warning(
                "SMTP is not configured (SMTP_HOST is empty); %r for %s was not "
                "sent.",
                subject,
                to,
            )
            return False

        headers = {}
        if config.reply_to_email:
            headers["Reply-To"] = config.reply_to_email
        message = emails.html(
            html=html,
            text=text,
            subject=subject,
            mail_from=(config.from_name, config.from_email),
            headers=headers or None,
        )

        transport = config.transport
        host = transport.host
        port = transport.port
        ssl = transport.encryption_mode == "ssl"
        tls = transport.encryption_mode == "starttls"
        user = transport.username
        password = transport.password

        # Only the environment transport gets the local Mailpit convenience:
        # a database profile is used exactly as the admin configured it.
        if (
            config.source == "environment"
            and not settings.is_production
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
            "timeout": transport.timeout_seconds,
            "fail_silently": False,
        }
        logger.info(
            "Sending %r to %s via resolved SMTP %s:%s (source=%s, tls=%s, "
            "ssl=%s, auth=%s)",
            subject,
            to,
            host,
            port,
            config.source,
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

    async def _deliver(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        link: str | None = None,
        event_key: str | None = None,
    ) -> bool:
        if self.resolver_provider is not None and event_key is not None:
            return await self._deliver_with_resolver(
                event_key,
                to=to,
                subject=subject,
                html=html,
                text=text,
                link=link,
            )

        if not settings.mail_enabled:
            # The link is a live credential. Echoing it is a local-convenience
            # feature only; a production misconfiguration must not write reset
            # tokens into the log.
            link_note = f" Link: {link}" if link and not settings.is_production else ""
            logger.warning(
                "SMTP is not configured (SMTP_HOST is empty); %r for %s was not "
                "sent.%s",
                subject,
                to,
                link_note,
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
