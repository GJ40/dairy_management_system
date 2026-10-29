from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.security import hash_password
from app.models.expense_category import ExpenseCategory
from app.models.user import User
from app.seeders.store import SeedStore

PRD_EXPENSE_CATEGORIES = (
    "feed",
    "labour",
    "medicine",
    "electricity",
    "transport",
    "other",
)


async def seed_database(
    store: SeedStore,
    *,
    settings_obj: Any = settings,
) -> dict[str, Any]:
    """Create the PRD expense categories and the initial admin user if missing."""

    created_categories: list[str] = []
    for name in PRD_EXPENSE_CATEGORIES:
        existing = await store.find(ExpenseCategory, name=name)
        if existing is None:
            await store.create(ExpenseCategory, name=name, is_deleted=False)
            created_categories.append(name)

    email = settings_obj.admin_email.strip().lower()
    admin = await store.find(User, email=email)
    admin_created = False
    if admin is None:
        admin = await store.create(
            User,
            full_name=settings_obj.admin_name,
            username=settings_obj.admin_username,
            email=email,
            password_hash=hash_password(
                settings_obj.admin_password.get_secret_value()
            ),
            role="admin",
            is_active=True,
            is_deleted=False,
        )
        admin_created = True

    await store.commit()
    return {
        "categories_created": created_categories,
        "admin_created": admin_created,
        "admin_email": email,
    }


async def _run() -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        summary = await seed_database(SeedStore(session))
    print(
        "[SEED] categories created: "
        f"{summary['categories_created'] or 'none'}; "
        f"admin created: {summary['admin_created']} ({summary['admin_email']})"
    )


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
