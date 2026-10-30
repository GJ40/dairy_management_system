from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from faker import Faker

from app.core.config import settings
from app.core.security import hash_password
from app.models.buffalo import Buffalo
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.models.invoice import Invoice
from app.models.invoice_sale import InvoiceSale
from app.models.milk_production import MilkProduction
from app.models.milk_wastage import MilkWastage
from app.models.sale import Sale
from app.models.user import User
from app.seeders.base_seed import seed_database
from app.seeders.store import SeedStore
from app.utils.time import get_business_date

CENT = Decimal("0.01")

INDIAN_BUFFALO_BREEDS = (
    "Murrah",
    "Surti",
    "Jaffarabadi",
    "Mehsana",
    "Nili-Ravi",
    "Bhadawari",
)

BUFFALO_NAMES = (
    "Gauri",
    "Lakshmi",
    "Yamuna",
    "Kalyani",
    "Ganga",
    "Champa",
    "Chameli",
    "Sita",
    "Radha",
    "Kaveri",
    "Bhavani",
    "Shakti",
)

OPERATORS = (
    {
        "full_name": "Ramesh Patel",
        "username": "ramesh_operator",
        "email": "ramesh.patel@dairyfarm.in",
    },
    {
        "full_name": "Suresh Kumar",
        "username": "suresh_operator",
        "email": "suresh.kumar@dairyfarm.in",
    },
    {
        "full_name": "Priya Sharma",
        "username": "priya_operator",
        "email": "priya.sharma@dairyfarm.in",
    },
)

EXPENSE_NOTES: dict[str, tuple[str, ...]] = {
    "feed": (
        "Cottonseed cake 50kg feed bag",
        "Green fodder (Barseem / Jowar) delivery",
        "Mineral mixture supplement 10kg",
        "Dry wheat straw trolley",
    ),
    "labour": (
        "Milking and shed cleaning weekly wage",
        "Cattle grazing support wage",
        "Night watch and feeding assistance",
    ),
    "medicine": (
        "Herd deworming bolus doses",
        "Mastitis prevention spray and treatment",
        "Calcium and vitamin H tonics",
        "Veterinary doctor consultation charge",
    ),
    "electricity": (
        "Chaff cutter and shed lighting electricity bill",
        "Borewell water pump power charges",
    ),
    "transport": (
        "Milk can transport to local collection centre",
        "Feed transport tractor freight charges",
    ),
    "other": (
        "Disinfectant lime powder for shed hygiene",
        "Stainless steel milking bucket replacement",
        "Rope, tether, and feeding tub maintenance",
    ),
}

DEFAULT_EXPENSE_NOTE = "General dairy farm expense"

BUFFALO_STATUSES = ("active",) * 9 + ("dry", "sold", "dead")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _full_name(faker: Any) -> str:
    """Support newer (``person.full_name``) and legacy (``name``) Faker APIs."""
    person = getattr(faker, "person", None)
    if person is not None:
        return person.full_name()
    legacy = getattr(faker, "name", None)
    if legacy is not None:
        return legacy()
    raise RuntimeError("Faker instance provides neither person nor name")


def _phone(faker: Any) -> str:
    for attr in ("phone_number", "phone"):
        provider = getattr(faker, attr, None)
        if provider is not None:
            return provider()
    raise RuntimeError("Faker instance provides no phone provider")


def _street_address(faker: Any) -> str:
    provider = getattr(faker, "street_address", None)
    if provider is not None:
        return provider()
    fallback = getattr(faker, "address", None)
    if fallback is not None:
        return fallback()
    raise RuntimeError("Faker instance provides no address provider")


def _city(faker: Any) -> str:
    provider = getattr(faker, "city", None)
    if provider is not None:
        return provider()
    return "Anand"


def _rate(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


async def seed_fake_indian_data(
    store: SeedStore,
    *,
    faker: Any | None = None,
    rng: random.Random | None = None,
    settings_obj: Any = settings,
) -> dict[str, Any]:
    faker = faker or Faker("en_IN")
    rng = rng or random.Random()

    base = await seed_database(store, settings_obj=settings_obj)

    admin = await store.find(User, role="admin")
    if admin is None:
        raise RuntimeError(
            "Admin user must exist before running fake data seeding."
        )

    created = {
        "operators": 0,
        "buffaloes": 0,
        "customers": 0,
        "production": 0,
        "wastage": 0,
        "sales": 0,
        "invoices": 0,
        "invoice_links": 0,
        "expenses": 0,
    }

    try:
        operator_hash = hash_password("Operator@123")
        operators: list[Any] = []
        for spec in OPERATORS:
            existing = await store.find(User, email=spec["email"])
            if existing is None:
                existing = await store.create(
                    User,
                    full_name=spec["full_name"],
                    username=spec["username"],
                    email=spec["email"],
                    password_hash=operator_hash,
                    role="operator",
                    is_active=True,
                    is_deleted=False,
                )
                created["operators"] += 1
            operators.append(existing)
        recorders = [admin, *operators]

        buffaloes: list[Any] = []
        for index, name in enumerate(BUFFALO_NAMES):
            tag_no = f"TAG-{101 + index:04d}"
            existing = await store.find(Buffalo, tag_no=tag_no)
            if existing is None:
                existing = await store.create(
                    Buffalo,
                    tag_no=tag_no,
                    name=name,
                    breed=INDIAN_BUFFALO_BREEDS[index % len(INDIAN_BUFFALO_BREEDS)],
                    dob=date(2020, 3, 15),
                    purchase_date=date(2022, 6, 10),
                    status=BUFFALO_STATUSES[index],
                    is_deleted=False,
                )
                created["buffaloes"] += 1
            buffaloes.append(existing)

        customers: list[Any] = []
        for index in range(8):
            full_name = _full_name(faker)
            existing = await store.find(Customer, name=full_name)
            if existing is None:
                existing = await store.create(
                    Customer,
                    name=full_name,
                    phone=_phone(faker),
                    address=(
                        f"{_street_address(faker)}, {_city(faker)}, Gujarat"
                    ),
                    rate_per_litre=_rate(60.0 + (index % 5) * 2.5),
                    is_active=index != 7,
                    is_deleted=False,
                )
                created["customers"] += 1
            customers.append(existing)

        today = date.fromisoformat(get_business_date())
        active_buffaloes = [
            buffalo for buffalo in buffaloes if buffalo.status == "active"
        ]

        for day_offset in range(5, -1, -1):
            prod_date = today - timedelta(days=day_offset)
            for buffalo in active_buffaloes:
                recorder = rng.choice(recorders)
                for session_name, low, spread in (
                    ("morning", 5.5, 3.5),
                    ("evening", 4.5, 3.0),
                ):
                    existing = await store.find(
                        MilkProduction,
                        buffalo_id=buffalo.id,
                        prod_date=prod_date,
                        session=session_name,
                    )
                    if existing is None:
                        await store.create(
                            MilkProduction,
                            buffalo_id=buffalo.id,
                            prod_date=prod_date,
                            session=session_name,
                            litres=_rate(low + rng.random() * spread),
                            recorded_by=recorder.id,
                            is_deleted=False,
                        )
                        created["production"] += 1

        wastage_date = today - timedelta(days=1)
        existing_wastage = await store.find(
            MilkWastage,
            waste_date=wastage_date,
            reason="spilled",
        )
        if existing_wastage is None:
            await store.create(
                MilkWastage,
                waste_date=wastage_date,
                litres=Decimal("2.50"),
                reason="spilled",
                recorded_by=admin.id,
                is_deleted=False,
            )
            created["wastage"] += 1

        active_customers = [
            customer for customer in customers if customer.is_active
        ]
        created_sales: list[Any] = []

        for day_offset in range(3, -1, -1):
            sale_date = today - timedelta(days=day_offset)
            for customer in active_customers[:4]:
                litres = _rate(4.0 + rng.random() * 6.0)
                rate = Decimal(str(customer.rate_per_litre))
                amount = _money(litres * rate)
                recorder = rng.choice(recorders)

                existing = await store.find(
                    Sale,
                    customer_id=customer.id,
                    sale_date=sale_date,
                    litres=litres,
                )
                if existing is None:
                    existing = await store.create(
                        Sale,
                        customer_id=customer.id,
                        sale_date=sale_date,
                        litres=litres,
                        rate=rate,
                        amount=amount,
                        payment_status="unpaid",
                        recorded_by=recorder.id,
                        is_deleted=False,
                    )
                    created["sales"] += 1
                created_sales.append(existing)

        if active_customers and created_sales:
            target_customer = active_customers[0]
            customer_sales = [
                sale
                for sale in created_sales
                if sale.customer_id == target_customer.id
            ]
            if customer_sales:
                total_amount = sum(
                    (Decimal(str(sale.amount)) for sale in customer_sales),
                    Decimal("0"),
                )
                invoice_no = f"INV-{today:%Y%m}-0001"
                invoice = await store.find(Invoice, invoice_no=invoice_no)
                created_invoice = False
                if invoice is None:
                    invoice = await store.create(
                        Invoice,
                        invoice_no=invoice_no,
                        customer_id=target_customer.id,
                        period_start=customer_sales[0].sale_date,
                        period_end=customer_sales[-1].sale_date,
                        total_amount=_money(total_amount),
                        paid_amount=_money(total_amount / 2),
                        status="partial",
                        is_deleted=False,
                    )
                    created_invoice = True
                    created["invoices"] += 1
                    await store.flush()

                if created_invoice:
                    for sale in customer_sales:
                        existing_link = await store.find(
                            InvoiceSale,
                            sale_id=sale.id,
                        )
                        if existing_link is None:
                            await store.create(
                                InvoiceSale,
                                invoice_id=invoice.id,
                                sale_id=sale.id,
                            )
                            created["invoice_links"] += 1

        categories = await store.find_all(ExpenseCategory)
        for category in categories:
            notes = EXPENSE_NOTES.get(category.name, (DEFAULT_EXPENSE_NOTE,))
            note = rng.choice(notes)
            amount = _rate(250.0 + rng.random() * 1200.0)
            expense_date = today - timedelta(days=rng.randint(0, 4))
            existing = await store.find(
                Expense,
                category_id=category.id,
                expense_date=expense_date,
                amount=amount,
            )
            if existing is None:
                await store.create(
                    Expense,
                    category_id=category.id,
                    expense_date=expense_date,
                    amount=amount,
                    note=note,
                    recorded_by=admin.id,
                    is_deleted=False,
                )
                created["expenses"] += 1

        await store.commit()
    except Exception:
        await store.rollback()
        raise

    return {"base": base, "created": created}


async def _run() -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        summary = await seed_fake_indian_data(SeedStore(session))
    print(f"[FAKER-SEED] created: {summary['created']}")


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
