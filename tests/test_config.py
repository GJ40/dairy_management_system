from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.core.config import Settings

JWT_SECRET = "a" * 40
CUSTOMER_SECRET = "b" * 40


def production_settings(**overrides) -> Settings:
    values = {
        "node_env": "production",
        "jwt_secret": JWT_SECRET,
        "customer_jwt_secret": CUSTOMER_SECRET,
        "admin_password": "A-strong-admin-password",
        "frontend_url": "https://dairy.example.com",
    }
    values.update(overrides)
    return Settings(**values)


class ProductionConfigTests(unittest.TestCase):
    def test_public_https_frontend_is_accepted(self) -> None:
        self.assertEqual(
            production_settings().frontend_base_url,
            "https://dairy.example.com",
        )

    def test_localhost_frontend_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "FRONTEND_URL must be the public"):
            production_settings(frontend_url="http://localhost:5173")

    def test_plain_http_frontend_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "FRONTEND_URL must be the public"):
            production_settings(frontend_url="http://dairy.example.com")


class CorsOriginTests(unittest.TestCase):
    def _settings(self, cors_origins: str) -> Settings:
        return Settings(node_env="development", cors_origins=cors_origins)

    def test_origins_are_split_and_trimmed(self) -> None:
        settings = self._settings(" http://localhost:5173 , http://localhost:3000 ")
        self.assertEqual(
            settings.cors_origin_list,
            ["http://localhost:5173", "http://localhost:3000"],
        )

    def test_trailing_slash_is_dropped(self) -> None:
        settings = self._settings("http://localhost:5173/")
        self.assertEqual(settings.cors_origin_list, ["http://localhost:5173"])

    def test_wildcard_is_kept_for_the_app_to_interpret(self) -> None:
        self.assertEqual(self._settings("*").cors_origin_list, ["*"])


class SecuritySettingsTests(unittest.TestCase):
    def test_proxy_trust_is_explicit(self) -> None:
        self.assertFalse(Settings(trust_proxy=False).trust_proxy)
        self.assertTrue(Settings(trust_proxy=True).trust_proxy)

    def test_audit_retention_is_bounded(self) -> None:
        self.assertEqual(Settings(audit_retention_days=30).audit_retention_days, 30)
        with self.assertRaises(ValidationError):
            Settings(audit_retention_days=29)
        with self.assertRaises(ValidationError):
            Settings(audit_retention_days=3651)


if __name__ == "__main__":
    unittest.main()
