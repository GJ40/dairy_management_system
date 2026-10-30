from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import jwt
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_customer_portal_account_repository,
    get_customer_repository,
    get_user_repository,
)
from app.core.security import (
    create_access_token,
    create_customer_access_token,
    create_customer_refresh_token,
    decode_access_token,
    decode_customer_access_token,
    decode_customer_refresh_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.main import app
from app.models.customer import Customer
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.customer_portal_account_event import CustomerPortalAccountEvent
from app.models.user import User
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_repository import CustomerRepository
from app.repositories.user_repository import UserRepository
from app.schemas.customer_portal_auth import (
    CreatePortalAccountRequest,
    PortalAccountQuery,
)
from app.services.customer_portal_auth_service import (
    CustomerPortalAccountService,
    CustomerPortalAuthService,
    hash_activation_token,
    issue_activation_token,
)
from app.utils.time import business_now_naive
from tests.test_phase3 import FakeUserRepository, make_user

CREATED = datetime(2026, 10, 30, 12, 0, 0)
PASSWORD = "customer-pass-123"
CUSTOMER_COOKIE = settings.customer_refresh_cookie_name
CUSTOMER_HINT = settings.customer_session_hint_cookie_name


def make_customer(
    customer_id: int = 4,
    *,
    name: str = "Ramesh Patil",
    is_active: bool = True,
    is_deleted: bool = False,
) -> Customer:
    return Customer(
        id=customer_id,
        name=name,
        phone="9876543210",
        address="Pune",
        rate_per_litre=Decimal("60.00"),
        is_active=is_active,
        is_deleted=is_deleted,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeCustomerRepository:
    def __init__(self, customers: list[Customer] | None = None) -> None:
        self.customers = list(customers or [])

    async def get_by_id(
        self,
        customer_id: int,
        *,
        include_deleted: bool = False,
    ) -> Customer | None:
        for customer in self.customers:
            if customer.id != customer_id:
                continue
            if include_deleted or not customer.is_deleted:
                return customer
        return None


class FakePortalAccountRepository:
    def __init__(self, accounts: list[CustomerPortalAccount] | None = None) -> None:
        self.accounts = list(accounts or [])
        self.events: list[CustomerPortalAccountEvent] = []
        self.commits = 0
        self.rollbacks = 0
        self._account_id = max((a.id for a in self.accounts), default=0) + 1
        self._event_id = 1

    async def get_by_id(
        self,
        account_id: int,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        for account in self.accounts:
            if account.id != account_id:
                continue
            if include_deleted or not account.is_deleted:
                return account
        return None

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        normalized = email.strip().lower()
        for account in self.accounts:
            if account.email != normalized:
                continue
            if include_deleted or not account.is_deleted:
                return account
        return None

    async def get_by_customer_id(
        self,
        customer_id: int,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        for account in self.accounts:
            if account.customer_id != customer_id:
                continue
            if include_deleted or not account.is_deleted:
                return account
        return None

    async def get_by_activation_hash(
        self,
        token_hash: str,
    ) -> CustomerPortalAccount | None:
        for account in self.accounts:
            if account.activation_token_hash == token_hash and not account.is_deleted:
                return account
        return None

    async def list_and_count(
        self,
        query: PortalAccountQuery,
    ) -> tuple[list[CustomerPortalAccount], int]:
        rows = [account for account in self.accounts if not account.is_deleted]
        if query.customer_id is not None:
            rows = [row for row in rows if row.customer_id == query.customer_id]
        if query.is_active is not None:
            rows = [row for row in rows if row.is_active is query.is_active]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        total = len(rows)
        start = (query.page - 1) * query.page_size
        return rows[start : start + query.page_size], total

    async def create(
        self,
        *,
        customer_id: int,
        email: str,
        activation_token_hash: str,
        activation_expires_at: datetime,
    ) -> CustomerPortalAccount:
        account = CustomerPortalAccount(
            id=self._account_id,
            customer_id=customer_id,
            email=email.strip().lower(),
            password_hash=None,
            is_active=True,
            activation_token_hash=activation_token_hash,
            activation_expires_at=activation_expires_at,
            activated_at=None,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        self._account_id += 1
        self.accounts.append(account)
        return account

    async def list_events(self, account_id: int) -> list[CustomerPortalAccountEvent]:
        rows = [event for event in self.events if event.account_id == account_id]
        return sorted(rows, key=lambda event: (event.created_at, event.id))

    async def add_event(
        self,
        *,
        account_id: int,
        action: str,
        actor_user_id: int | None,
        note: str | None = None,
    ) -> CustomerPortalAccountEvent:
        event = CustomerPortalAccountEvent(
            id=self._event_id,
            account_id=account_id,
            action=action,
            actor_user_id=actor_user_id,
            note=note,
            created_at=CREATED + timedelta(seconds=self._event_id),
        )
        self._event_id += 1
        self.events.append(event)
        return event

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, account: CustomerPortalAccount) -> None:
        return None


def make_account(
    account_id: int = 1,
    *,
    customer_id: int = 4,
    email: str = "customer@example.com",
    password: str | None = None,
    is_active: bool = True,
    activated: bool = False,
    token: str | None = None,
    expires_at: datetime | None = None,
) -> CustomerPortalAccount:
    return CustomerPortalAccount(
        id=account_id,
        customer_id=customer_id,
        email=email,
        password_hash=hash_password(password) if password else None,
        is_active=is_active,
        activation_token_hash=hash_activation_token(token) if token else None,
        activation_expires_at=expires_at,
        activated_at=CREATED if activated else None,
        last_login_at=None,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeSession:
    def __init__(
        self,
        accounts: list[CustomerPortalAccount],
        customers: list[Customer],
        users: list[User] | None = None,
    ) -> None:
        self.accounts = accounts
        self.customers = customers
        self.users = list(users or [])

    async def get(self, model: type, ident: int):
        if model is CustomerPortalAccount:
            return next((row for row in self.accounts if row.id == ident), None)
        if model is Customer:
            return next((row for row in self.customers if row.id == ident), None)
        if model is User:
            return next((row for row in self.users if row.id == ident), None)
        return None


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.accounts = FakePortalAccountRepository()
        self.service = CustomerPortalAuthService(self.accounts, self.customers)
        self.admin_service = CustomerPortalAccountService(
            self.accounts, self.customers
        )

    async def _provision_and_get_token(self) -> tuple[CustomerPortalAccount, str]:
        result = await self.admin_service.provision(
            CreatePortalAccountRequest(
                customer_id=self.customer.id,
                email="Customer@Example.com ",
            ),
            actor_user_id=1,
        )
        return self.accounts.accounts[0], result["activation"]["token"]

    async def test_provision_creates_account_and_audit_event(self) -> None:
        account, token = await self._provision_and_get_token()
        self.assertEqual(account.email, "customer@example.com")
        self.assertIsNone(account.password_hash)
        self.assertIsNone(account.activated_at)
        self.assertIsNotNone(account.activation_token_hash)
        self.assertNotEqual(account.activation_token_hash, token)
        self.assertEqual(account.activation_token_hash, hash_activation_token(token))
        self.assertEqual(self.accounts.events[0].action, "provisioned")
        self.assertEqual(self.accounts.events[0].actor_user_id, 1)

    async def test_provision_rejects_duplicate_customer_and_email(self) -> None:
        await self._provision_and_get_token()
        with self.assertRaises(HTTPException) as customer_error:
            await self.admin_service.provision(
                CreatePortalAccountRequest(customer_id=4, email="other@example.com"),
                actor_user_id=1,
            )
        self.assertEqual(customer_error.exception.status_code, 409)
        self.assertEqual(customer_error.exception.detail["code"], "ACCOUNT_EXISTS")

        self.customer2 = make_customer(5, name="Second")
        self.customers.customers.append(self.customer2)
        with self.assertRaises(HTTPException) as email_error:
            await self.admin_service.provision(
                CreatePortalAccountRequest(
                    customer_id=5, email="customer@example.com"
                ),
                actor_user_id=1,
            )
        self.assertEqual(email_error.exception.detail["code"], "EMAIL_IN_USE")

    async def test_provision_rejects_inactive_customer(self) -> None:
        self.customer.is_active = False
        with self.assertRaises(HTTPException) as error:
            await self.admin_service.provision(
                CreatePortalAccountRequest(customer_id=4, email="a@example.com"),
                actor_user_id=1,
            )
        self.assertEqual(error.exception.detail["code"], "CUSTOMER_INACTIVE")

    async def test_activate_sets_password_and_consumes_token(self) -> None:
        account, token = await self._provision_and_get_token()
        result = await self.service.activate(token, PASSWORD)
        self.assertTrue(verify_password(PASSWORD, account.password_hash))
        self.assertIsNotNone(account.activated_at)
        self.assertIsNone(account.activation_token_hash)
        self.assertIsNone(account.activation_expires_at)
        self.assertEqual(result["message"][:16], "Portal account a")
        self.assertEqual(self.accounts.events[-1].action, "activated")

    async def test_activate_reuse_and_expiry(self) -> None:
        with self.assertRaises(HTTPException) as reuse:
            await self.service.activate("not-a-real-token", PASSWORD)
        self.assertEqual(reuse.exception.detail["code"], "INVALID_ACTIVATION_TOKEN")

        token, token_hash, _ = issue_activation_token()
        account = make_account(token=token, expires_at=business_now_naive() - timedelta(minutes=1))
        account.activation_token_hash = token_hash
        self.accounts.accounts.append(account)
        with self.assertRaises(HTTPException) as expired:
            await self.service.activate(token, PASSWORD)
        self.assertEqual(
            expired.exception.detail["code"], "ACTIVATION_TOKEN_EXPIRED"
        )

    async def test_activate_rejects_weak_password_and_already_activated(self) -> None:
        _, token = await self._provision_and_get_token()
        with self.assertRaises(HTTPException) as weak:
            await self.service.activate(token, "short")
        self.assertEqual(weak.exception.detail["code"], "WEAK_PASSWORD")

        account = self.accounts.accounts[0]
        account.password_hash = hash_password(PASSWORD)
        with self.assertRaises(HTTPException) as already:
            await self.service.activate(token, PASSWORD)
        self.assertEqual(already.exception.detail["code"], "ALREADY_ACTIVATED")

    async def test_login_issues_tokens_and_rejects_bad_credentials(self) -> None:
        account, token = await self._provision_and_get_token()
        await self.service.activate(token, PASSWORD)

        session = await self.service.login("CUSTOMER@example.com ", PASSWORD)
        self.assertTrue(session["access_token"])
        self.assertTrue(session["refresh_token"])
        self.assertNotIn("password_hash", session["account"])
        self.assertEqual(session["account"]["customer"]["rate_per_litre"], "60.00")
        self.assertIsNotNone(account.last_login_at)

        for email, password in (
            ("customer@example.com", "wrong-password"),
            ("unknown@example.com", PASSWORD),
        ):
            with self.subTest(email=email):
                with self.assertRaises(HTTPException) as error:
                    await self.service.login(email, password)
                self.assertEqual(error.exception.status_code, 401)
                self.assertEqual(
                    error.exception.detail["message"], "Invalid email or password"
                )

    async def test_login_rejects_inactive_or_unactivated(self) -> None:
        account, token = await self._provision_and_get_token()
        with self.assertRaises(HTTPException):
            await self.service.login("customer@example.com", PASSWORD)

        await self.service.activate(token, PASSWORD)
        account.is_active = False
        with self.assertRaises(HTTPException):
            await self.service.login("customer@example.com", PASSWORD)

        account.is_active = True
        self.customer.is_active = False
        with self.assertRaises(HTTPException):
            await self.service.login("customer@example.com", PASSWORD)

    async def test_refresh_issues_new_access_token(self) -> None:
        account, token = await self._provision_and_get_token()
        await self.service.activate(token, PASSWORD)
        session = await self.service.login("customer@example.com", PASSWORD)

        refreshed = await self.service.refresh(session["refresh_token"])
        self.assertTrue(refreshed["access_token"])
        claims = decode_customer_access_token(refreshed["access_token"])
        self.assertEqual(claims["account_id"], account.id)
        self.assertEqual(claims["customer_id"], self.customer.id)

        with self.assertRaises(HTTPException) as error:
            await self.service.refresh(session["access_token"])
        self.assertEqual(error.exception.detail["code"], "UNAUTHORIZED")

    async def test_deactivate_reactivate_and_reset(self) -> None:
        account, token = await self._provision_and_get_token()
        await self.service.activate(token, PASSWORD)

        with self.assertRaises(HTTPException) as already:
            await self.admin_service.reset_activation(account.id, actor_user_id=1)
        self.assertEqual(already.exception.detail["code"], "ALREADY_ACTIVATED")

        await self.admin_service.deactivate(account.id, "Customer request", 1)
        self.assertFalse(account.is_active)
        self.assertIsNone(account.activation_token_hash)
        self.assertEqual(self.accounts.events[-1].action, "deactivated")
        self.assertEqual(self.accounts.events[-1].note, "Customer request")

        with self.assertRaises(HTTPException):
            await self.service.login("customer@example.com", PASSWORD)

        result = await self.admin_service.reactivate(account.id, actor_user_id=1)
        self.assertTrue(account.is_active)
        self.assertIsNone(account.password_hash)
        self.assertIsNone(account.activated_at)
        self.assertIn("token", result["activation"])
        self.assertEqual(self.accounts.events[-1].action, "reactivated")


class TokenSeparationTests(unittest.TestCase):
    def test_customer_and_staff_tokens_are_not_interchangeable(self) -> None:
        staff_token = create_access_token(
            user_id=1,
            email="admin@example.com",
            username="admin",
            role="admin",
        )
        customer_token = create_customer_access_token(
            account_id=1,
            customer_id=4,
            email="customer@example.com",
        )
        with self.assertRaises(jwt.InvalidTokenError):
            decode_access_token(customer_token)
        with self.assertRaises(jwt.InvalidTokenError):
            decode_customer_access_token(staff_token)

    def test_customer_refresh_token_requires_customer_type(self) -> None:
        refresh = create_customer_refresh_token(
            account_id=1,
            customer_id=4,
            email="customer@example.com",
        )
        claims = decode_customer_refresh_token(refresh)
        self.assertEqual(claims["type"], "customer_refresh")
        self.assertEqual(claims["scope"], "customer")
        self.assertEqual(claims["aud"], "customer-portal")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(
            user_id=2,
            email="operator@example.com",
            username="operator",
            full_name="Milk Operator",
            role="operator",
        )
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.accounts = FakePortalAccountRepository()
        self.users = FakeUserRepository([self.admin, self.operator])

        async def override_get_db():
            yield FakeSession(
                self.accounts.accounts,
                self.customers.customers,
                self.users.users,
            )

        def override_account_repository() -> CustomerPortalAccountRepository:
            return self.accounts  # type: ignore[return-value]

        def override_customer_repository() -> CustomerRepository:
            return self.customers  # type: ignore[return-value]

        def override_user_repository() -> UserRepository:
            return self.users  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_portal_account_repository] = (
            override_account_repository
        )
        app.dependency_overrides[get_customer_repository] = (
            override_customer_repository
        )
        app.dependency_overrides[get_user_repository] = override_user_repository

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _staff_auth(self, user: User | None = None) -> dict[str, str]:
        target = user or self.admin
        token = create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=staff-session",
        }

    async def _provision(self) -> dict:
        response = await self.client.post(
            "/api/v1/customer-portal-accounts",
            json={"customer_id": self.customer.id, "email": "customer@example.com"},
            headers=self._staff_auth(),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def _activate(self) -> None:
        provisioned = await self._provision()
        response = await self.client.post(
            "/api/v1/customer-auth/activate",
            json={"token": provisioned["activation"]["token"], "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)

    async def _login(self) -> httpx.Response:
        response = await self.client.post(
            "/api/v1/customer-auth/login",
            json={"email": "customer@example.com", "password": PASSWORD},
        )
        self.client.cookies.clear()
        return response

    def _cookie_value(self, response: httpx.Response, name: str) -> str:
        for raw in response.headers.get_list("set-cookie"):
            if raw.startswith(f"{name}="):
                return raw.split(";", 1)[0].split("=", 1)[1]
        return ""

    async def test_full_activation_login_me_logout_flow(self) -> None:
        provisioned = await self._provision()
        self.assertIn("token", provisioned["activation"])
        self.assertNotIn("password_hash", provisioned["account"])
        self.assertNotIn("activation_token_hash", provisioned["account"])

        activation = await self.client.post(
            "/api/v1/customer-auth/activate",
            json={"token": provisioned["activation"]["token"], "password": PASSWORD},
        )
        self.assertEqual(activation.status_code, 200, activation.text)
        self.assertNotIn("access_token", activation.json())

        login = await self._login()
        self.assertEqual(login.status_code, 200, login.text)
        body = login.json()
        self.assertNotIn("refresh_token", body)
        token_cookie = self._cookie_value(login, CUSTOMER_COOKIE)
        hint_cookie = self._cookie_value(login, CUSTOMER_HINT)
        self.assertTrue(token_cookie)
        self.assertEqual(hint_cookie, "1")

        me = await self.client.get(
            "/api/v1/customer-auth/me",
            headers={
                "Authorization": f"Bearer {body['access_token']}",
                "Cookie": f"{CUSTOMER_COOKIE}={token_cookie}",
            },
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["account"]["email"], "customer@example.com")

        logout = await self.client.post("/api/v1/customer-auth/logout")
        self.assertEqual(logout.status_code, 200)
        for name in (CUSTOMER_COOKIE, CUSTOMER_HINT):
            raw = next(
                (c for c in logout.headers.get_list("set-cookie") if c.startswith(f"{name}=")),
                "",
            )
            self.assertIn("max-age=0", raw.lower())

    async def test_me_requires_customer_cookie_and_rejects_staff_token(self) -> None:
        await self._activate()
        login = await self._login()
        access = login.json()["access_token"]

        missing_cookie = await self.client.get(
            "/api/v1/customer-auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        self.assertEqual(missing_cookie.status_code, 401)

        staff_token = create_access_token(
            user_id=1,
            email="admin@example.com",
            username="admin",
            role="admin",
        )
        wrong_token = await self.client.get(
            "/api/v1/customer-auth/me",
            headers={
                "Authorization": f"Bearer {staff_token}",
                "Cookie": f"{CUSTOMER_COOKIE}=anything",
            },
        )
        self.assertEqual(wrong_token.status_code, 401)

    async def test_refresh_uses_customer_cookie_only(self) -> None:
        await self._activate()
        login = await self._login()
        cookie = self._cookie_value(login, CUSTOMER_COOKIE)

        refreshed = await self.client.post(
            "/api/v1/customer-auth/refresh",
            headers={"Cookie": f"{CUSTOMER_COOKIE}={cookie}"},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertTrue(refreshed.json()["access_token"])

        no_cookie = await self.client.post("/api/v1/customer-auth/refresh")
        self.assertEqual(no_cookie.status_code, 401)
        self.assertIn("max-age=0", no_cookie.headers.get("set-cookie", "").lower())

    async def test_account_admin_requires_admin_for_mutation(self) -> None:
        denied = await self.client.post(
            "/api/v1/customer-portal-accounts",
            json={"customer_id": 4, "email": "customer@example.com"},
            headers=self._staff_auth(self.operator),
        )
        self.assertEqual(denied.status_code, 403)

        listing = await self.client.get(
            "/api/v1/customer-portal-accounts",
            headers=self._staff_auth(self.operator),
        )
        self.assertEqual(listing.status_code, 200, listing.text)

    async def test_deactivate_requires_reason_and_blocks_guard(self) -> None:
        await self._activate()
        login = await self._login()
        access = login.json()["access_token"]
        cookie = self._cookie_value(login, CUSTOMER_COOKIE)

        bad = await self.client.post(
            "/api/v1/customer-portal-accounts/1/deactivate",
            json={"reason": "x"},
            headers=self._staff_auth(),
        )
        self.assertEqual(bad.status_code, 400)

        deactivated = await self.client.post(
            "/api/v1/customer-portal-accounts/1/deactivate",
            json={"reason": "Customer asked to close the portal"},
            headers=self._staff_auth(),
        )
        self.assertEqual(deactivated.status_code, 200, deactivated.text)

        blocked = await self.client.get(
            "/api/v1/customer-auth/me",
            headers={
                "Authorization": f"Bearer {access}",
                "Cookie": f"{CUSTOMER_COOKIE}={cookie}",
            },
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["error"]["code"], "ACCOUNT_INACTIVE")

    async def test_customer_token_is_rejected_by_staff_routes(self) -> None:
        await self._activate()
        login = await self._login()
        response = await self.client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {login.json()['access_token']}",
                "Cookie": f"{settings.refresh_cookie_name}=staff-session",
            },
        )
        self.assertEqual(response.status_code, 401)


class OpenApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_customer_auth_routes_documented(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            spec = (await client.get("/api/v1/docs/openapi.json")).json()

        paths = spec["paths"]
        for path, method in (
            ("/api/v1/customer-auth/activate", "post"),
            ("/api/v1/customer-auth/login", "post"),
            ("/api/v1/customer-auth/refresh", "post"),
            ("/api/v1/customer-auth/logout", "post"),
            ("/api/v1/customer-auth/me", "get"),
            ("/api/v1/customer-portal-accounts", "get"),
            ("/api/v1/customer-portal-accounts", "post"),
            ("/api/v1/customer-portal-accounts/{account_id}", "get"),
            ("/api/v1/customer-portal-accounts/{account_id}/reactivate", "post"),
            ("/api/v1/customer-portal-accounts/{account_id}/deactivate", "post"),
            ("/api/v1/customer-portal-accounts/{account_id}/reset-activation", "post"),
        ):
            with self.subTest(path=path, method=method):
                self.assertIn(method, paths[path])
        self.assertIn("CustomerBearerAuth", spec["components"]["securitySchemes"])


if __name__ == "__main__":
    unittest.main()
