from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.email_service import EmailService


class EmailServiceLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def _send(self) -> tuple[bool, str]:
        url = "http://localhost:5173/reset-password?token=super-secret-token"
        with self.assertLogs("app.services.email_service", level="WARNING") as logs:
            sent = await EmailService().send_password_reset(
                to="asha@example.com",
                name="Asha",
                reset_url=url,
                audience="staff",
            )
        return sent, "\n".join(logs.output)

    async def test_unconfigured_smtp_in_development_logs_the_link(self) -> None:
        with patch.object(settings, "smtp_host", ""), patch.object(
            settings, "node_env", "development"
        ):
            sent, output = await self._send()

        self.assertFalse(sent)
        self.assertIn("SMTP is not configured", output)
        self.assertIn("token=super-secret-token", output)

    async def test_unconfigured_smtp_in_production_hides_the_link(self) -> None:
        with patch.object(settings, "smtp_host", ""), patch.object(
            settings, "node_env", "production"
        ):
            sent, output = await self._send()

        self.assertFalse(sent)
        self.assertIn("SMTP is not configured", output)
        self.assertNotIn("super-secret-token", output)


if __name__ == "__main__":
    unittest.main()
