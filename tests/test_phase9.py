from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.dependencies import (
    get_expense_category_repository,
    get_expense_repository,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.models.user import User
from app.schemas.expense import (
    UNSET,
    CreateExpenseRequest,
    ExpenseQuery,
    UpdateExpenseRequest,
)
from app.schemas.expense_category import CreateExpenseCategoryRequest
from app.services.expense_category_service import ExpenseCategoryService
from app.services.expense_service import ExpenseService

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)


def make_user(
    user_id: int = 1,
    *,
    role: str = "admin",
    username: str = "admin",
) -> User:
    return User(
        id=user_id,
        full_name="System Admin" if role == "admin" else "Ramesh Patel",
        username=username,
        email=f"{username}@example.com",
        password_hash="not-used",
        role=role,
        is_active=True,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_category(category_id: int = 1, *, name: str = "feed") -> ExpenseCategory:
    return ExpenseCategory(
        id=category_id,
        name=name,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_expense(
    expense_id: int = 1,
    *,
    category_id: int = 1,
    expense_date: str = "2026-10-28",
    amount: str = "1200.00",
    note: str | None = "Feed purchase",
    recorded_by: int = 1,
) -> Expense:
    return Expense(
        id=expense_id,
        category_id=category_id,
        expense_date=date.fromisoformat(expense_date),
        amount=Decimal(amount),
        note=note,
        recorded_by=recorded_by,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeExpenseCategoryRepository:
    def __init__(self) -> None:
        self.categories: dict[int, ExpenseCategory] = {}
        self.next_id = 1

    def seed(self, category: ExpenseCategory) -> None:
        self.categories[category.id] = category
        self.next_id = max(self.next_id, category.id + 1)

    async def get_by_id(self, category_id: int) -> ExpenseCategory | None:
        category = self.categories.get(category_id)
        if category is None or category.is_deleted:
            return None
        return category

    async def list_active(self) -> list[ExpenseCategory]:
        return [
            category
            for category in sorted(
                self.categories.values(), key=lambda row: row.name
            )
            if not category.is_deleted
        ]

    async def find_by_name(self, name: str) -> ExpenseCategory | None:
        return next(
            (
                category
                for category in self.categories.values()
                if category.name == name and not category.is_deleted
            ),
            None,
        )

    async def create(self, *, name: str) -> ExpenseCategory:
        category = ExpenseCategory(
            id=self.next_id,
            name=name,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        self.next_id += 1
        self.categories[category.id] = category
        return category


class FakeExpenseRepository:
    def __init__(self, categories: FakeExpenseCategoryRepository) -> None:
        self.categories = categories
        self.expenses: dict[int, Expense] = {}
        self.next_id = 1
        self.commits = 0
        self.rollbacks = 0

    async def get_by_id(self, expense_id: int) -> Expense | None:
        expense = self.expenses.get(expense_id)
        if expense is None or expense.is_deleted:
            return None
        expense.category = self.categories.categories.get(expense.category_id)
        expense.recorder = None
        return expense

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        category_id: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> tuple[list[Expense], int, Decimal]:
        rows = [row for row in self.expenses.values() if not row.is_deleted]
        if category_id is not None:
            rows = [row for row in rows if row.category_id == category_id]
        if from_date is not None and to_date is not None:
            rows = [
                row
                for row in rows
                if from_date <= row.expense_date.isoformat() <= to_date
            ]
        elif from_date is not None:
            rows = [row for row in rows if row.expense_date.isoformat() >= from_date]
        elif to_date is not None:
            rows = [row for row in rows if row.expense_date.isoformat() <= to_date]
        rows.sort(key=lambda row: (row.expense_date, row.created_at), reverse=True)
        total = len(rows)
        total_amount = sum((row.amount for row in rows), Decimal("0"))
        for row in rows:
            row.category = self.categories.categories.get(row.category_id)
            row.recorder = None
        start = (page - 1) * page_size
        return rows[start : start + page_size], total, total_amount

    async def create(
        self,
        *,
        category_id: int,
        expense_date: date,
        amount: Decimal,
        note: str | None,
        recorded_by: int,
    ) -> Expense:
        expense = Expense(
            id=self.next_id,
            category_id=category_id,
            expense_date=expense_date,
            amount=amount,
            note=note,
            recorded_by=recorded_by,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        self.next_id += 1
        self.expenses[expense.id] = expense
        return expense

    async def update(self, expense: Expense, updates: dict) -> Expense:
        for key, value in updates.items():
            setattr(expense, key, value)
        return expense

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


def build_services() -> tuple[
    FakeExpenseCategoryRepository,
    FakeExpenseRepository,
    ExpenseCategoryService,
    ExpenseService,
    User,
]:
    admin = make_user()
    category_repository = FakeExpenseCategoryRepository()
    category_repository.seed(make_category(1))
    expense_repository = FakeExpenseRepository(category_repository)
    return (
        category_repository,
        expense_repository,
        ExpenseCategoryService(category_repository),
        ExpenseService(expense_repository, category_repository),
        admin,
    )


class CategorySchemaTests(unittest.TestCase):
    def test_create_category_validation(self) -> None:
        cases = [
            ({}, "Field required"),
            ({"name": ""}, "Category name must be at least 2 characters long"),
            ({"name": "A"}, "Category name must be at least 2 characters long"),
            ({"name": 12}, "Invalid input: expected string, received number"),
            ({"name": "x" * 81}, "Category name cannot exceed 80 characters"),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    CreateExpenseCategoryRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))

    def test_category_name_is_normalized(self) -> None:
        payload = CreateExpenseCategoryRequest.model_validate(
            {"name": "  Cattle FEED  "}
        )
        self.assertEqual(payload.name, "cattle feed")


class ExpenseSchemaTests(unittest.TestCase):
    def test_create_expense_validation(self) -> None:
        cases = [
            ({}, "Field required"),
            (
                {"category_id": 0, "expense_date": "2026-10-28", "amount": 10},
                "category_id must be a positive integer",
            ),
            (
                {"category_id": 1, "expense_date": "bad", "amount": 10},
                "expense_date must be in YYYY-MM-DD format",
            ),
            (
                {"category_id": 1, "expense_date": "2026-10-28", "amount": 0},
                "amount must be greater than zero",
            ),
            (
                {
                    "category_id": 1,
                    "expense_date": "2026-10-28",
                    "amount": 1000000000,
                },
                "amount exceeds maximum allowable threshold",
            ),
            (
                {
                    "category_id": 1,
                    "expense_date": "2026-10-28",
                    "amount": 10,
                    "note": "x" * 1001,
                },
                "Too big: expected string to have <=1000 characters",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    CreateExpenseRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))

    def test_optional_note_defaults(self) -> None:
        payload = CreateExpenseRequest.model_validate(
            {
                "category_id": "1",
                "expense_date": "2026-10-28",
                "amount": "250.5",
                "note": "   ",
            }
        )
        self.assertEqual(payload.category_id, 1)
        self.assertEqual(payload.amount, 250.5)
        self.assertIsNone(payload.note)

        without_note = CreateExpenseRequest.model_validate(
            {"category_id": 1, "expense_date": "2026-10-28", "amount": 1}
        )
        self.assertIs(without_note.note, UNSET)

    def test_update_expense_validation(self) -> None:
        with self.assertRaises(Exception) as caught:
            UpdateExpenseRequest.model_validate(
                {"amount": 0, "expense_date": "2026-10-28"}
            )
        self.assertIn("amount must be greater than zero", str(caught.exception))

        empty = UpdateExpenseRequest.model_validate({})
        self.assertIs(empty.amount, UNSET)
        self.assertIs(empty.note, UNSET)


class CategoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.category_repository,
            _,
            self.service,
            _,
            _,
        ) = build_services()

    async def test_list_and_create(self) -> None:
        listing = await self.service.list_categories()
        self.assertEqual(len(listing["categories"]), 1)
        self.assertEqual(listing["categories"][0]["name"], "feed")
        self.assertIn("createdAt", listing["categories"][0])

        created = await self.service.create_category(
            CreateExpenseCategoryRequest.model_validate({"name": "  Fuel  "})
        )
        self.assertEqual(created["category"]["name"], "fuel")

        with self.assertRaises(HTTPException) as caught:
            await self.service.create_category(
                CreateExpenseCategoryRequest.model_validate({"name": "FUEL"})
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "DUPLICATE_CATEGORY")
        self.assertEqual(
            caught.exception.detail["message"],
            "Expense category 'fuel' already exists",
        )


class ExpenseServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.category_repository,
            self.expense_repository,
            _,
            self.service,
            self.admin,
        ) = build_services()

    async def test_list_and_get(self) -> None:
        await self.expense_repository.create(
            category_id=1,
            expense_date=date(2026, 10, 28),
            amount=Decimal("1200.00"),
            note="feed",
            recorded_by=1,
        )
        await self.expense_repository.create(
            category_id=1,
            expense_date=date(2026, 10, 29),
            amount=Decimal("800.00"),
            note=None,
            recorded_by=1,
        )

        result = await self.service.list_expenses(
            ExpenseQuery(page=1, page_size=10)
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["total_pages"], 1)
        self.assertEqual(result["total_expense_amount"], "2000.00")
        self.assertEqual(result["items"][0]["amount"], "800.00")
        self.assertEqual(result["items"][0]["expense_date"], "2026-10-29")
        self.assertEqual(result["items"][1]["category"]["name"], "feed")
        self.assertIsNone(result["items"][1]["recorder"])

        detail = await self.service.get_expense("1")
        self.assertEqual(detail["expense"]["amount"], "1200.00")

        filtered = await self.service.list_expenses(
            ExpenseQuery(page=1, page_size=10, from_date="2026-10-29")
        )
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["total_expense_amount"], "800.00")

        with self.assertRaises(HTTPException) as caught:
            await self.service.get_expense("99")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            caught.exception.detail["message"], "Expense with id 99 not found"
        )

    async def test_create_and_update(self) -> None:
        payload = CreateExpenseRequest.model_validate(
            {
                "category_id": 1,
                "expense_date": "2026-10-28",
                "amount": 500,
                "note": "  feed oct  ",
            }
        )
        created = await self.service.create_expense(payload, self.admin.id)
        self.assertEqual(created["expense"]["amount"], "500.00")
        self.assertEqual(created["expense"]["note"], "feed oct")
        self.assertEqual(created["expense"]["recorded_by"], 1)
        self.assertEqual(
            created["expense"]["category"], {"id": 1, "name": "feed"}
        )
        self.assertEqual(self.expense_repository.commits, 1)

        update = await self.service.update_expense(
            "1",
            UpdateExpenseRequest.model_validate({"amount": 600, "note": "updated"}),
        )
        self.assertEqual(update["expense"]["amount"], "600.00")
        self.assertEqual(update["expense"]["note"], "updated")

        cleared = await self.service.update_expense(
            "1",
            UpdateExpenseRequest.model_validate(
                {"note": None, "category_id": 1}
            ),
        )
        self.assertIsNone(cleared["expense"]["note"])
        self.assertEqual(cleared["expense"]["amount"], "600.00")

        with self.assertRaises(HTTPException) as caught:
            await self.service.update_expense(
                "1", UpdateExpenseRequest.model_validate({"category_id": 99})
            )
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            caught.exception.detail["message"],
            "Expense category with id 99 not found",
        )

    async def test_create_requires_category(self) -> None:
        payload = CreateExpenseRequest.model_validate(
            {"category_id": 42, "expense_date": "2026-10-28", "amount": 10}
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.create_expense(payload, self.admin.id)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            caught.exception.detail["message"],
            "Expense category with id 42 not found",
        )


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.category_repository,
            self.expense_repository,
            _,
            _,
            self.admin,
        ) = build_services()
        self.operator = make_user(
            2, role="operator", username="ramesh_operator"
        )

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_expense_category_repository] = (
            lambda: self.category_repository
        )
        app.dependency_overrides[get_expense_repository] = (
            lambda: self.expense_repository
        )
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
        return {"Authorization": f"Bearer {token}"}

    async def test_categories(self) -> None:
        listing = await self.client.get(
            "/api/v1/expenses/categories", headers=self._auth()
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["categories"]), 1)
        self.assertEqual(listing.json()["categories"][0]["name"], "feed")

        alias = await self.client.get(
            "/api/v1/expense-categories", headers=self._auth()
        )
        self.assertEqual(alias.status_code, 200)
        self.assertEqual(
            [row["name"] for row in alias.json()["categories"]], ["feed"]
        )

        created = await self.client.post(
            "/api/v1/expenses/categories",
            headers=self._auth(),
            json={"name": "Fuel "},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["category"]["name"], "fuel")

        duplicate = await self.client.post(
            "/api/v1/expenses/categories",
            headers=self._auth(),
            json={"name": "fuel"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["error"]["code"], "DUPLICATE_CATEGORY"
        )

        invalid = await self.client.post(
            "/api/v1/expenses/categories",
            headers=self._auth(),
            json={"name": "x"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            invalid.json()["error"]["message"],
            "name: Category name must be at least 2 characters long",
        )

    async def test_expense_crud(self) -> None:
        created = await self.client.post(
            "/api/v1/expenses",
            headers=self._auth(),
            json={
                "category_id": 1,
                "expense_date": "2026-10-28",
                "amount": 1500.5,
            },
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()["expense"]
        self.assertEqual(body["amount"], "1500.50")
        self.assertIsNone(body["note"])
        self.assertEqual(body["category"]["id"], 1)
        self.assertEqual(body["recorded_by"], 1)

        missing_category = await self.client.post(
            "/api/v1/expenses",
            headers=self._auth(),
            json={"category_id": 99, "expense_date": "2026-10-28", "amount": 10},
        )
        self.assertEqual(missing_category.status_code, 404)
        self.assertEqual(
            missing_category.json()["error"]["message"],
            "Expense category with id 99 not found",
        )

        listing = await self.client.get(
            "/api/v1/expenses?category_id=1", headers=self._auth()
        )
        self.assertEqual(listing.status_code, 200)
        data = listing.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["total_pages"], 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(data["total_expense_amount"], "1500.50")

        detail = await self.client.get(
            f"/api/v1/expenses/{body['id']}", headers=self._auth()
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["expense"]["amount"], "1500.50")

        updated = await self.client.put(
            f"/api/v1/expenses/{body['id']}",
            headers=self._auth(),
            json={"note": "updated note", "amount": 1600},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["expense"]["note"], "updated note")
        self.assertEqual(updated.json()["expense"]["amount"], "1600.00")

        missing = await self.client.get(
            "/api/v1/expenses/999", headers=self._auth()
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.json()["error"]["message"], "Expense with id 999 not found"
        )

        unauthenticated = await self.client.get("/api/v1/expenses")
        self.assertEqual(unauthenticated.status_code, 401)

    async def test_operator_is_forbidden(self) -> None:
        for url in (
            "/api/v1/expenses",
            "/api/v1/expenses/categories",
            "/api/v1/expense-categories",
        ):
            with self.subTest(url=url):
                response = await self.client.get(
                    url, headers=self._auth(self.operator)
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["error"]["message"],
                    "Access denied: Requires one of [admin] role",
                )

    async def test_validation_messages(self) -> None:
        body_cases = [
            (
                {},
                "category_id: Invalid input: expected number, received NaN",
            ),
            (
                {"category_id": 1, "expense_date": "2026-10-28", "amount": 0},
                "amount: amount must be greater than zero",
            ),
        ]
        for payload, expected in body_cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/expenses",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"], expected
                )

        query_cases = [
            (
                "/api/v1/expenses?from=bad",
                "from: from must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/expenses?to=bad",
                "to: to must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/expenses?category_id=0",
                "category_id: Too small: expected number to be >0",
            ),
            (
                "/api/v1/expenses?page_size=101",
                "page_size: Too big: expected number to be <=100",
            ),
        ]
        for url, expected in query_cases:
            with self.subTest(url=url):
                response = await self.client.get(url, headers=self._auth())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"], expected
                )


if __name__ == "__main__":
    unittest.main()
