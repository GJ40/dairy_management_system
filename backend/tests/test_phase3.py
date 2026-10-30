from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import HTTPException
from pydantic import ValidationError

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import get_user_repository
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    CreateUserRequest,
    UpdateUserRequest,
    UserQuery,
    serialize_user,
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService

PASSWORD = "password123"
CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)


def make_user(
    user_id: int = 1,
    *,
    email: str = "admin@example.com",
    username: str = "admin",
    full_name: str = "System Admin",
    role: str = "admin",
    is_active: bool = True,
    is_deleted: bool = False,
    password: str = PASSWORD,
) -> User:
    return User(
        id=user_id,
        full_name=full_name,
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = list(users or [])
        self.commits = 0
        self.rollbacks = 0
        self._next_id = max((user.id for user in self.users), default=0) + 1

    async def get_by_id(self, user_id: int, *, include_deleted: bool = False) -> User | None:
        for user in self.users:
            if user.id == user_id and (include_deleted or not user.is_deleted):
                return user
        return None

    async def get_by_email(
        self,
        email: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> User | None:
        normalized = email.strip().lower()
        for user in self.users:
            if exclude_id is not None and user.id == exclude_id:
                continue
            if user.email == normalized and (include_deleted or not user.is_deleted):
                return user
        return None

    async def get_by_username(
        self,
        username: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> User | None:
        normalized = username.strip()
        for user in self.users:
            if exclude_id is not None and user.id == exclude_id:
                continue
            if user.username == normalized and (include_deleted or not user.is_deleted):
                return user
        return None

    async def list_users(self, query: UserQuery) -> tuple[list[User], int]:
        users = [user for user in self.users if not user.is_deleted]
        if query.role:
            users = [user for user in users if user.role == query.role]
        if query.is_active is not None:
            users = [user for user in users if user.is_active is query.is_active]
        if query.search:
            term = query.search.lower()
            users = [
                user
                for user in users
                if term in user.full_name.lower()
                or term in user.username.lower()
                or term in user.email.lower()
            ]
        users.sort(key=lambda user: user.created_at, reverse=True)
        total = len(users)
        start = (query.page - 1) * query.page_size
        return users[start : start + query.page_size], total

    async def create(
        self,
        *,
        full_name: str,
        username: str,
        email: str,
        password_hash: str,
        role: str,
    ) -> User:
        user = User(
            id=self._next_id,
            full_name=full_name,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        self._next_id += 1
        self.users.append(user)
        return user

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, user: User) -> None:
        return None


class SecurityTests(unittest.TestCase):
    def test_password_hash_and_verify(self) -> None:
        hashed = hash_password(PASSWORD)
        self.assertTrue(hashed.startswith("$2b$10$"))
        self.assertTrue(verify_password(PASSWORD, hashed))
        self.assertFalse(verify_password("wrong-password", hashed))
        self.assertFalse(verify_password(PASSWORD, "not-a-hash"))

    def test_password_is_truncated_like_bcrypt(self) -> None:
        first = "a" * 72 + "X"
        second = "a" * 72 + "Y"
        hashed = hash_password(first)
        self.assertTrue(verify_password(second, hashed))

    def test_access_token_payload(self) -> None:
        token = create_access_token(
            user_id=7,
            email="admin@example.com",
            username="admin",
            role="admin",
        )
        payload = decode_access_token(token)
        self.assertEqual(payload["id"], 7)
        self.assertEqual(payload["email"], "admin@example.com")
        self.assertEqual(payload["username"], "admin")
        self.assertEqual(payload["role"], "admin")
        self.assertIsInstance(payload["iat"], int)
        self.assertIsInstance(payload["exp"], int)
        self.assertEqual(payload["exp"] - payload["iat"], settings.jwt_expire_minutes * 60)

    def test_expired_token(self) -> None:
        now = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = jwt.encode(
            {
                "id": 1,
                "email": "admin@example.com",
                "username": "admin",
                "role": "admin",
                "iat": now,
                "exp": now,
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_invalid_token(self) -> None:
        with self.assertRaises(jwt.InvalidTokenError):
            decode_access_token("not-a-jwt")


class SerializationTests(unittest.TestCase):
    def test_camel_case_timestamps(self) -> None:
        data = serialize_user(make_user())
        self.assertEqual(data["createdAt"], "2026-10-28T06:40:23.123Z")
        self.assertEqual(data["updatedAt"], "2026-10-28T06:40:23.123Z")
        self.assertNotIn("created_at", data)
        self.assertNotIn("password_hash", data)

    def test_snake_case_timestamps_for_me(self) -> None:
        data = serialize_user(make_user(), snake_timestamps=True)
        self.assertEqual(data["created_at"], "2026-10-28T06:40:23.123Z")
        self.assertEqual(data["updated_at"], "2026-10-28T06:40:23.123Z")
        self.assertNotIn("createdAt", data)


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.repository = FakeUserRepository([self.admin])
        self.service = AuthService(self.repository)

    async def test_login_success(self) -> None:
        result = await self.service.login("ADMIN@EXAMPLE.COM ", PASSWORD)
        self.assertIn("access_token", result)
        self.assertNotIn("token", result)
        self.assertEqual(result["user"]["email"], "admin@example.com")
        self.assertEqual(result["user"]["createdAt"], "2026-10-28T06:40:23.123Z")
        self.assertNotIn("password_hash", result["user"])
        payload = decode_access_token(result["access_token"])
        self.assertEqual(payload["id"], self.admin.id)

    async def test_login_wrong_password(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Invalid email or password"):
            await self.service.login("admin@example.com", "wrong")

    async def test_login_unknown_email(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Invalid email or password"):
            await self.service.login("missing@example.com", PASSWORD)

    async def test_login_inactive(self) -> None:
        self.admin.is_active = False
        with self.assertRaisesRegex(
            HTTPException,
            "Account is deactivated. Please contact an administrator.",
        ):
            await self.service.login("admin@example.com", PASSWORD)

    async def test_login_deleted_is_generic(self) -> None:
        self.admin.is_deleted = True
        with self.assertRaisesRegex(HTTPException, "Invalid email or password"):
            await self.service.login("admin@example.com", PASSWORD)

    async def test_get_me_uses_snake_timestamps(self) -> None:
        result = await self.service.get_me(self.admin.id)
        self.assertEqual(result["created_at"], "2026-10-28T06:40:23.123Z")
        self.assertNotIn("createdAt", result)

    async def test_get_me_deleted(self) -> None:
        self.admin.is_deleted = True
        with self.assertRaisesRegex(HTTPException, "User profile not found"):
            await self.service.get_me(self.admin.id)


class UserServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(
            user_id=2,
            email="operator@example.com",
            username="operator",
            full_name="Milk Operator",
            role="operator",
        )
        self.deleted = make_user(
            user_id=3,
            email="deleted@example.com",
            username="deleted",
            full_name="Deleted User",
            role="operator",
            is_deleted=True,
        )
        self.repository = FakeUserRepository([self.admin, self.operator, self.deleted])
        self.service = UserService(self.repository)

    async def test_list_filters_and_paginates(self) -> None:
        result = await self.service.list_users(UserQuery(page=1, page_size=1))
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 1)

        operators = await self.service.list_users(UserQuery(role="operator"))
        self.assertEqual([item["username"] for item in operators["items"]], ["operator"])

        search = await self.service.list_users(UserQuery(search="milk"))
        self.assertEqual([item["username"] for item in search["items"]], ["operator"])

        active = await self.service.list_users(UserQuery(is_active=False))
        self.assertEqual(active["total"], 0)

    async def test_get_user(self) -> None:
        result = await self.service.get_user(str(self.operator.id))
        self.assertEqual(result["username"], "operator")

    async def test_get_user_invalid_id(self) -> None:
        with self.assertRaisesRegex(HTTPException, "User with id abc not found"):
            await self.service.get_user("abc")

    async def test_get_user_missing(self) -> None:
        with self.assertRaisesRegex(HTTPException, "User with id 999 not found"):
            await self.service.get_user("999")

    async def test_create_user_normalizes_and_hashes(self) -> None:
        payload = CreateUserRequest(
            full_name="  New User  ",
            username="  newuser  ",
            email="  NEW@EXAMPLE.COM ",
            password="secret123",
            role="operator",
        )
        result = await self.service.create_user(payload)
        self.assertEqual(result["full_name"], "New User")
        self.assertEqual(result["username"], "newuser")
        self.assertEqual(result["email"], "new@example.com")
        self.assertEqual(result["role"], "operator")
        self.assertTrue(result["is_active"])
        self.assertNotIn("password_hash", result)
        created = await self.repository.get_by_email("new@example.com")
        self.assertIsNotNone(created)
        self.assertTrue(verify_password("secret123", created.password_hash))

    async def test_create_duplicate_email(self) -> None:
        payload = CreateUserRequest(
            full_name="Other",
            username="other",
            email="ADMIN@EXAMPLE.COM",
            password="secret123",
            role="operator",
        )
        with self.assertRaisesRegex(
            HTTPException,
            "A user with this email address already exists",
        ):
            await self.service.create_user(payload)

    async def test_create_duplicate_username(self) -> None:
        payload = CreateUserRequest(
            full_name="Other",
            username=" admin ",
            email="other@example.com",
            password="secret123",
            role="operator",
        )
        with self.assertRaisesRegex(
            HTTPException,
            "A user with this username already exists",
        ):
            await self.service.create_user(payload)

    async def test_update_user(self) -> None:
        payload = UpdateUserRequest(
            full_name="  Updated Operator ",
            username=" operator2 ",
            email=" OPERATOR2@EXAMPLE.COM ",
            password="newpassword",
            role="admin",
        )
        result = await self.service.update_user(str(self.operator.id), payload)
        self.assertEqual(result["full_name"], "Updated Operator")
        self.assertEqual(result["username"], "operator2")
        self.assertEqual(result["email"], "operator2@example.com")
        self.assertEqual(result["role"], "admin")
        self.assertTrue(verify_password("newpassword", self.operator.password_hash))

    async def test_update_duplicate_username(self) -> None:
        payload = UpdateUserRequest(username="admin")
        with self.assertRaisesRegex(
            HTTPException,
            "Username is already taken by another user",
        ):
            await self.service.update_user(str(self.operator.id), payload)

    async def test_update_duplicate_email(self) -> None:
        payload = UpdateUserRequest(email="ADMIN@EXAMPLE.COM")
        with self.assertRaisesRegex(
            HTTPException,
            "Email is already registered to another user",
        ):
            await self.service.update_user(str(self.operator.id), payload)

    async def test_update_user_missing(self) -> None:
        with self.assertRaisesRegex(HTTPException, "User with id 999 not found"):
            await self.service.update_user("999", UpdateUserRequest(full_name="X"))

    async def test_update_status(self) -> None:
        result = await self.service.update_status(str(self.operator.id), False, self.admin.id)
        self.assertFalse(result["is_active"])
        result = await self.service.update_status(str(self.operator.id), True, self.admin.id)
        self.assertTrue(result["is_active"])

    async def test_cannot_deactivate_self(self) -> None:
        with self.assertRaisesRegex(
            HTTPException,
            "Administrators cannot deactivate their own account",
        ):
            await self.service.update_status(str(self.admin.id), False, self.admin.id)

    async def test_update_rejects_explicit_null(self) -> None:
        with self.assertRaises(ValidationError):
            UpdateUserRequest(full_name=None)

    async def test_delete_operator_soft_deletes(self) -> None:
        result = await self.service.delete_user(str(self.operator.id), self.admin.id)
        self.assertEqual(result["resource"], "users")
        self.assertEqual(result["id"], self.operator.id)
        self.assertIn("deleted_at", result)
        self.assertTrue(self.operator.is_deleted)
        self.assertFalse(self.operator.is_active)
        self.assertGreater(self.repository.commits, 0)
        self.assertEqual(self.repository.rollbacks, 0)

        listing = await self.service.list_users(UserQuery())
        self.assertNotIn(
            "operator",
            [item["username"] for item in listing["items"]],
        )

    async def test_delete_inactive_operator_allowed(self) -> None:
        self.operator.is_active = False
        result = await self.service.delete_user(str(self.operator.id), self.admin.id)
        self.assertEqual(result["id"], self.operator.id)
        self.assertTrue(self.operator.is_deleted)

    async def test_delete_missing_or_invalid_id(self) -> None:
        with self.assertRaisesRegex(HTTPException, "User with id 999 not found"):
            await self.service.delete_user("999", self.admin.id)
        with self.assertRaisesRegex(HTTPException, "User with id abc not found"):
            await self.service.delete_user("abc", self.admin.id)

    async def test_delete_admin_account_blocked(self) -> None:
        other_admin = make_user(
            user_id=4,
            email="admin2@example.com",
            username="admin2",
            full_name="Second Admin",
        )
        self.repository.users.append(other_admin)
        with self.assertRaisesRegex(
            HTTPException,
            "Only operator accounts can be deleted",
        ):
            await self.service.delete_user(str(other_admin.id), self.admin.id)
        self.assertFalse(other_admin.is_deleted)

    async def test_cannot_delete_self(self) -> None:
        with self.assertRaisesRegex(
            HTTPException,
            "Administrators cannot delete their own account",
        ):
            await self.service.delete_user(str(self.admin.id), self.admin.id)
        self.assertFalse(self.admin.is_deleted)


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User and self.user is not None and self.user.id == user_id:
            return self.user
        return None


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
        self.inactive = make_user(
            user_id=3,
            email="inactive@example.com",
            username="inactive",
            full_name="Inactive User",
            role="operator",
            is_active=False,
        )
        self.repository = FakeUserRepository([self.admin, self.operator, self.inactive])
        self.current_user: User | None = self.admin

        async def override_get_db():
            yield FakeSession(self.current_user)

        def override_repository() -> UserRepository:
            return self.repository  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_user_repository] = override_repository
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, user: User | None = None) -> dict[str, str]:
        target = user or self.admin
        token = create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=test-session",
        }

    async def test_login_success(self) -> None:
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"email": "ADMIN@EXAMPLE.COM ", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertNotIn("token", body)
        self.assertEqual(
            list(body["user"]),
            [
                "id",
                "full_name",
                "username",
                "email",
                "role",
                "is_active",
                "is_deleted",
                "createdAt",
                "updatedAt",
            ],
        )
        self.assertNotIn("password_hash", body["user"])

    async def test_login_wrong_password(self) -> None:
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"error": {"code": "UNAUTHORIZED", "message": "Invalid email or password"}},
        )

    async def test_login_inactive(self) -> None:
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@example.com", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Account is deactivated. Please contact an administrator.",
        )

    async def test_auth_me(self) -> None:
        response = await self.client.get("/api/v1/auth/me", headers=self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.json()["user"]),
            [
                "id",
                "full_name",
                "username",
                "email",
                "role",
                "is_active",
                "is_deleted",
                "created_at",
                "updated_at",
            ],
        )

    async def test_auth_me_missing_header(self) -> None:
        response = await self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Missing or malformed Authorization header",
        )

    async def test_auth_me_invalid_token(self) -> None:
        response = await self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Invalid authentication token",
        )

    async def test_auth_me_expired_token(self) -> None:
        now = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = jwt.encode(
            {
                "id": self.admin.id,
                "email": self.admin.email,
                "username": self.admin.username,
                "role": self.admin.role,
                "iat": now,
                "exp": now,
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        response = await self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "Authentication token has expired",
        )

    async def test_auth_me_user_missing(self) -> None:
        self.current_user = None
        response = await self.client.get(
            "/api/v1/auth/me",
            headers=self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "User account not found",
        )

    async def test_auth_me_user_deactivated(self) -> None:
        self.current_user = self.inactive
        response = await self.client.get(
            "/api/v1/auth/me",
            headers=self._auth(self.inactive),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["message"],
            "User account is deactivated",
        )

    async def test_operator_forbidden(self) -> None:
        self.current_user = self.operator
        response = await self.client.get(
            "/api/v1/users",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Access denied: Requires one of [admin] role",
                }
            },
        )

    async def test_admin_lists_users(self) -> None:
        response = await self.client.get("/api/v1/users", headers=self._auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(body["total"], 3)

    async def test_create_user(self) -> None:
        response = await self.client.post(
            "/api/v1/users",
            headers=self._auth(),
            json={
                "full_name": " New User ",
                "username": " newuser ",
                "email": " NEW@EXAMPLE.COM ",
                "password": "secret123",
                "role": "operator",
            },
        )
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual(user["username"], "newuser")
        self.assertEqual(user["email"], "new@example.com")
        self.assertNotIn("password_hash", user)

    async def test_create_duplicate_email(self) -> None:
        response = await self.client.post(
            "/api/v1/users",
            headers=self._auth(),
            json={
                "full_name": "Other",
                "username": "other",
                "email": "admin@example.com",
                "password": "secret123",
                "role": "operator",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["message"],
            "A user with this email address already exists",
        )

    async def test_create_validation_missing_fields(self) -> None:
        response = await self.client.post(
            "/api/v1/users",
            headers=self._auth(),
            json={"username": "newuser", "email": "new@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            body["error"]["message"],
            "full_name: Invalid input: expected string, received undefined",
        )

    async def test_create_validation_short_password(self) -> None:
        response = await self.client.post(
            "/api/v1/users",
            headers=self._auth(),
            json={
                "full_name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "password": "short",
                "role": "operator",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "password: Password must be at least 6 characters",
        )

    async def test_create_validation_role(self) -> None:
        response = await self.client.post(
            "/api/v1/users",
            headers=self._auth(),
            json={
                "full_name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "password": "secret123",
                "role": "owner",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            'role: Invalid option: expected one of "admin"|"operator"',
        )

    async def test_invalid_page_size(self) -> None:
        response = await self.client.get(
            "/api/v1/users?page_size=101",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "page_size: Too big: expected number to be <=100",
        )

    async def test_get_user_not_found(self) -> None:
        response = await self.client.get("/api/v1/users/999", headers=self._auth())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["message"],
            "User with id 999 not found",
        )

    async def test_update_duplicate_username(self) -> None:
        response = await self.client.put(
            f"/api/v1/users/{self.operator.id}",
            headers=self._auth(),
            json={"username": "admin"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["message"],
            "Username is already taken by another user",
        )

    async def test_self_deactivation(self) -> None:
        response = await self.client.patch(
            f"/api/v1/users/{self.admin.id}/status",
            headers=self._auth(),
            json={"is_active": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "Administrators cannot deactivate their own account",
        )

    async def test_admin_deletes_operator(self) -> None:
        response = await self.client.delete(
            f"/api/v1/users/{self.operator.id}",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["resource"], "users")
        self.assertEqual(body["id"], self.operator.id)
        self.assertEqual(body["message"], f"User #{self.operator.id} deleted successfully")
        self.assertTrue(self.operator.is_deleted)
        self.assertFalse(self.operator.is_active)

        listing = await self.client.get("/api/v1/users", headers=self._auth())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listing.json()["items"]],
            [self.admin.id, self.inactive.id],
        )

        # A soft-deleted user is hidden and can no longer be fetched or deleted.
        missing = await self.client.delete(
            f"/api/v1/users/{self.operator.id}",
            headers=self._auth(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.json()["error"]["message"],
            f"User with id {self.operator.id} not found",
        )

    async def test_delete_operator_requires_admin(self) -> None:
        self.current_user = self.operator
        forbidden = await self.client.delete(
            f"/api/v1/users/{self.inactive.id}",
            headers=self._auth(self.operator),
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            forbidden.json()["error"]["message"],
            "Access denied: Requires one of [admin] role",
        )
        self.assertFalse(self.inactive.is_deleted)

        unauthenticated = await self.client.delete(
            f"/api/v1/users/{self.inactive.id}"
        )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertFalse(self.inactive.is_deleted)

    async def test_delete_admin_account_blocked_endpoint(self) -> None:
        other_admin = make_user(
            user_id=4,
            email="admin2@example.com",
            username="admin2",
            full_name="Second Admin",
        )
        self.repository.users.append(other_admin)

        response = await self.client.delete(
            f"/api/v1/users/{other_admin.id}",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "BAD_REQUEST")
        self.assertIn(
            "Only operator accounts can be deleted",
            response.json()["error"]["message"],
        )
        self.assertFalse(other_admin.is_deleted)

    async def test_cannot_delete_own_account_endpoint(self) -> None:
        response = await self.client.delete(
            f"/api/v1/users/{self.admin.id}",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "Administrators cannot delete their own account",
        )
        self.assertFalse(self.admin.is_deleted)

    async def test_status_requires_boolean(self) -> None:
        response = await self.client.patch(
            f"/api/v1/users/{self.operator.id}/status",
            headers=self._auth(),
            json={"is_active": "false"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "is_active: Invalid input: expected boolean, received string",
        )


if __name__ == "__main__":
    unittest.main()
