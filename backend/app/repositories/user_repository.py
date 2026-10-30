from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserQuery


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int, *, include_deleted: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if not include_deleted:
            statement = statement.where(User.is_deleted.is_(False))
        return await self.session.scalar(statement)

    async def get_by_email(
        self,
        email: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(User.email == email.strip().lower())
        if not include_deleted:
            statement = statement.where(User.is_deleted.is_(False))
        if exclude_id is not None:
            statement = statement.where(User.id != exclude_id)
        return await self.session.scalar(statement)

    async def get_by_username(
        self,
        username: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(User.username == username.strip())
        if not include_deleted:
            statement = statement.where(User.is_deleted.is_(False))
        if exclude_id is not None:
            statement = statement.where(User.id != exclude_id)
        return await self.session.scalar(statement)

    async def list_users(self, query: UserQuery) -> tuple[list[User], int]:
        conditions = [User.is_deleted.is_(False)]
        if query.role:
            conditions.append(User.role == query.role)
        if query.is_active is not None:
            conditions.append(User.is_active.is_(query.is_active))
        if query.search:
            term = f"%{query.search}%"
            conditions.append(
                or_(
                    User.full_name.like(term),
                    User.username.like(term),
                    User.email.like(term),
                )
            )

        count_statement = select(func.count()).select_from(User).where(*conditions)
        total = int(await self.session.scalar(count_statement) or 0)

        offset = (query.page - 1) * query.page_size
        statement = (
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(query.page_size)
        )
        rows = list(await self.session.scalars(statement))
        return rows, total

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
            full_name=full_name,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            is_deleted=False,
        )
        self.session.add(user)
        return user

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, user: User) -> None:
        await self.session.refresh(user)
