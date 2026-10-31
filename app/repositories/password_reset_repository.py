from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken


class PasswordResetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        scope: str,
        subject_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        record = PasswordResetToken(
            scope=scope,
            subject_id=subject_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        statement = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        return await self.session.scalar(statement)

    async def invalidate_outstanding(
        self,
        *,
        scope: str,
        subject_id: int,
        now: datetime,
    ) -> None:
        """Burn every unused link for this subject before issuing a new one."""
        statement = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.scope == scope,
                PasswordResetToken.subject_id == subject_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        await self.session.execute(statement)

    async def consume(self, token_id: int, *, now: datetime) -> bool:
        """Atomically mark the token used.

        The `used_at IS NULL` predicate in the UPDATE is what makes the token
        one-time-use even when two requests submit it at the same moment.
        """
        statement = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.id == token_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        result = await self.session.execute(statement)
        return bool(result.rowcount)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
