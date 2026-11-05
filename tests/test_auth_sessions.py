from __future__ import annotations

import unittest

import httpx

from app.core.config import Settings, settings
from app.core.dependencies import get_login_security_service, get_user_repository
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.repositories.user_repository import UserRepository
from tests.test_auth_and_users import (
    FakeLoginSecurityService,
    FakeSession,
    FakeUserRepository,
    make_user,
)

COOKIE = settings.refresh_cookie_name
HINT = settings.session_hint_cookie_name


class AuthRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(
            user_id=2,
            email="operator@example.com",
            username="operator",
            full_name="Milk Operator",
            role="operator",
        )
        self.repository = FakeUserRepository([self.admin, self.operator])
        self.current_user: User | None = self.admin

        async def override_get_db():
            yield FakeSession(self.current_user)

        def override_repository() -> UserRepository:
            return self.repository  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_user_repository] = override_repository
        app.dependency_overrides[get_login_security_service] = lambda: (
            FakeLoginSecurityService()
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _refresh_token(self, user: User | None = None) -> str:
        target = user or self.admin
        return create_refresh_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )

    def _access_token(self, user: User | None = None) -> str:
        target = user or self.admin
        return create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )

    def _cookie(self, response: httpx.Response, name: str) -> str:
        for raw in response.headers.get_list("set-cookie"):
            if raw.startswith(f"{name}="):
                return raw
        return ""

    def _assert_expired(self, response: httpx.Response, name: str) -> None:
        cookie = self._cookie(response, name)
        self.assertTrue(cookie, f"no {name} cookie in {response.headers}")
        lowered = cookie.lower()
        self.assertTrue(
            "max-age=0" in lowered or "expires=thu, 01 jan 1970" in lowered,
            cookie,
        )

    def _cookie_header(self, value: str) -> dict[str, str]:
        return {"Cookie": f"{COOKIE}={value}"}

    async def _refresh(self, **kwargs) -> httpx.Response:
        return await self.client.post("/api/v1/auth/refresh", **kwargs)

    def _assert_new_access_token(self, response: httpx.Response) -> None:
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["access_token"])
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(
            body["expires_in"],
            settings.access_token_expire_minutes * 60,
        )
        self.assertEqual(body["user"]["email"], self.admin.email)
        # The refresh token only ever travels back as a cookie, and the access
        # token is not also echoed under a second name.
        self.assertNotIn("refresh_token", body)
        self.assertNotIn("token", body)

    async def test_refresh_with_cookie(self) -> None:
        response = await self._refresh(
            headers=self._cookie_header(self._refresh_token())
        )
        self._assert_new_access_token(response)
        # Nothing to re-issue: the cookie is already in place.
        self.assertEqual(response.headers.get_list("set-cookie"), [])

    def test_cookie_path_is_widened_to_reach_guarded_routes(self) -> None:
        # A path the browser would not send to /api/v1/customers would 401
        # every guarded route, so it is widened to the API prefix instead.
        narrowed = Settings(refresh_cookie_path="/api/v1/auth")
        self.assertEqual(narrowed.refresh_cookie_path, narrowed.api_v1_prefix)
        self.assertEqual(Settings(refresh_cookie_path="/").refresh_cookie_path, "/")
        self.assertEqual(
            Settings(refresh_cookie_path="api").refresh_cookie_path,
            "/api",
        )

    async def test_access_token_without_refresh_cookie_is_rejected(self) -> None:
        response = await self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self._access_token()}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Refresh token cookie is missing; sign in again",
        )

    async def test_access_token_with_refresh_cookie_is_accepted(self) -> None:
        response = await self.client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                **self._cookie_header(self._refresh_token()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["email"], self.admin.email)

    async def test_refresh_ignores_json_body_and_header(self) -> None:
        # The token is cookie-only: neither a body nor a bearer header counts.
        response = await self._refresh(
            json={"refresh_token": self._refresh_token()},
            headers={"Authorization": f"Bearer {self._refresh_token()}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Refresh token not provided",
        )

    async def test_refresh_missing_token(self) -> None:
        response = await self._refresh()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Refresh token not provided",
        )
        # A stale hint cookie must not survive a tokenless refresh.
        self._assert_expired(response, HINT)

    async def test_each_refresh_issues_a_new_access_token(self) -> None:
        headers = self._cookie_header(self._refresh_token())
        first = (await self._refresh(headers=headers)).json()["access_token"]
        second = (await self._refresh(headers=headers)).json()["access_token"]
        self.assertNotEqual(first, second)

    async def test_refresh_rejects_access_token(self) -> None:
        response = await self._refresh(
            headers=self._cookie_header(self._access_token())
        )
        self.assertEqual(response.status_code, 401)
        message = response.json()["error"]["message"]
        self.assertIn("access token", message)
        self.assertIn("refresh token", message)
        # The rejected cookie was the session, so it is dropped.
        self._assert_expired(response, COOKIE)
        self._assert_expired(response, HINT)

    async def test_refresh_rejects_garbage_token(self) -> None:
        response = await self._refresh(headers=self._cookie_header("not-a-jwt"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["message"], "Invalid refresh token")

    async def test_dead_cookie_is_cleared(self) -> None:
        response = await self._refresh(headers=self._cookie_header("not-a-jwt"))
        self.assertEqual(response.status_code, 401)
        self._assert_expired(response, COOKIE)
        self._assert_expired(response, HINT)

    async def test_refresh_for_deleted_user(self) -> None:
        token = self._refresh_token(self.operator)
        self.repository.users.remove(self.operator)
        response = await self._refresh(headers=self._cookie_header(token))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "User account not found",
        )

    async def test_refresh_rejects_a_token_issued_before_a_password_reset(
        self,
    ) -> None:
        token = create_refresh_token(
            user_id=self.admin.id,
            email=self.admin.email,
            username=self.admin.username,
            role=self.admin.role,
            token_version=0,
        )
        # A reset bumps the column; the old cookie must stop working.
        self.admin.token_version = 1

        response = await self._refresh(headers=self._cookie_header(token))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Session has expired; sign in again",
        )
        self._assert_expired(response, COOKIE)

    async def test_access_token_from_before_a_password_reset_is_rejected(
        self,
    ) -> None:
        access = create_access_token(
            user_id=self.admin.id,
            email=self.admin.email,
            username=self.admin.username,
            role=self.admin.role,
            token_version=0,
        )
        refresh = self._refresh_token()
        self.admin.token_version = 1

        response = await self.client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {access}",
                **self._cookie_header(refresh),
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Session has expired; sign in again",
        )

    async def test_login_sets_refresh_and_hint_cookies(self) -> None:
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("refresh_token", response.json())
        self.assertNotIn("token", response.json())
        self.assertTrue(response.json()["access_token"])

        token_cookie = self._cookie(response, COOKIE)
        self.assertIn("httponly", token_cookie.lower())
        self.assertIn(f"path={settings.refresh_cookie_path}", token_cookie.lower())
        self.assertIn(
            f"max-age={settings.refresh_cookie_max_age}", token_cookie.lower()
        )

        # The flag cookie holds no secret, is JS-readable and site-wide.
        hint_cookie = self._cookie(response, HINT)
        self.assertTrue(hint_cookie.startswith(f"{HINT}=1"), hint_cookie)
        self.assertNotIn("httponly", hint_cookie.lower())
        self.assertTrue(
            "path=/;" in hint_cookie.lower() or hint_cookie.lower().endswith("path=/"),
            hint_cookie,
        )

    async def test_logout_clears_both_cookies(self) -> None:
        response = await self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Logged out"})

        for name in (COOKIE, HINT):
            with self.subTest(cookie=name):
                self._assert_expired(response, name)

    async def test_openapi_documents_refresh_as_cookie_only(self) -> None:
        spec = (await self.client.get("/api/v1/docs/openapi.json")).json()
        schemes = spec["components"]["securitySchemes"]

        self.assertEqual(schemes["BearerAuth"]["scheme"], "bearer")
        self.assertNotIn("RefreshTokenAuth", schemes)

        # No Authorization lock and no request body: the cookie is the input.
        refresh = spec["paths"]["/api/v1/auth/refresh"]["post"]
        self.assertNotIn("security", refresh)
        self.assertNotIn("requestBody", refresh)

        # Protected routes keep using the access-token scheme only.
        customers = spec["paths"]["/api/v1/customers"]["get"]
        self.assertEqual(customers["security"], [{"BearerAuth": []}])


if __name__ == "__main__":
    unittest.main()
