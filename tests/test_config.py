from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
