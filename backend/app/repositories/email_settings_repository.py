from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_notification_recipient import EmailNotificationRecipient
from app.models.email_sender_identity import EmailSenderIdentity
from app.models.email_smtp_profile import EmailSmtpProfile
from app.models.email_workflow_mapping import EmailWorkflowMapping
from app.models.security_audit_event import SecurityAuditEvent

SMTP_PROFILE_RESOURCE = "email_smtp_profile"
SENDER_IDENTITY_RESOURCE = "email_sender_identity"
WORKFLOW_MAPPING_RESOURCE = "email_workflow_mapping"
RECIPIENT_RESOURCE = "email_notification_recipient"


class EmailSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_profiles(self) -> list[EmailSmtpProfile]:
        statement = select(EmailSmtpProfile).order_by(
            EmailSmtpProfile.active_slot.desc(),
            EmailSmtpProfile.updated_at.desc(),
            EmailSmtpProfile.id.desc(),
        )
        return list((await self.session.scalars(statement)).all())

    async def get_profile(self, profile_id: int) -> EmailSmtpProfile | None:
        return await self.session.get(EmailSmtpProfile, profile_id)

    async def get_active_profile(self) -> EmailSmtpProfile | None:
        statement = select(EmailSmtpProfile).where(
            EmailSmtpProfile.active_slot == 1
        )
        return await self.session.scalar(statement)

    async def get_profile_for_update(self, profile_id: int) -> EmailSmtpProfile | None:
        """Lock one profile row for the activation transaction."""
        statement = (
            select(EmailSmtpProfile)
            .where(EmailSmtpProfile.id == profile_id)
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_active_profile_for_update(self) -> EmailSmtpProfile | None:
        statement = (
            select(EmailSmtpProfile)
            .where(EmailSmtpProfile.active_slot == 1)
            .with_for_update()
        )
        return await self.session.scalar(statement)

    # ------------------------------------------------------------------
    # Test rate limiting (counted from the security audit ledger, in UTC)
    # ------------------------------------------------------------------
    async def latest_test_action_at(
        self,
        *,
        actor_user_id: int,
        profile_id: int,
        event_types: Sequence[str],
        cutoff: datetime,
    ) -> datetime | None:
        """Most recent test action by this admin for this profile, if recent."""
        statement = select(func.max(SecurityAuditEvent.created_at)).where(
            SecurityAuditEvent.actor_user_id == actor_user_id,
            SecurityAuditEvent.event_type.in_(tuple(event_types)),
            SecurityAuditEvent.resource_type == SMTP_PROFILE_RESOURCE,
            SecurityAuditEvent.resource_id == str(profile_id),
            SecurityAuditEvent.created_at >= cutoff,
        )
        return await self.session.scalar(statement)

    async def count_test_actions(
        self,
        *,
        actor_user_id: int,
        since: datetime,
        event_types: Sequence[str],
    ) -> int:
        statement = (
            select(func.count())
            .select_from(SecurityAuditEvent)
            .where(
                SecurityAuditEvent.actor_user_id == actor_user_id,
                SecurityAuditEvent.event_type.in_(tuple(event_types)),
                SecurityAuditEvent.created_at >= since,
            )
        )
        return int(await self.session.scalar(statement) or 0)

    # ------------------------------------------------------------------
    # Sender identities
    # ------------------------------------------------------------------
    async def list_senders(self) -> list[EmailSenderIdentity]:
        statement = select(EmailSenderIdentity).order_by(
            func.lower(EmailSenderIdentity.display_name).asc(),
            EmailSenderIdentity.id.asc(),
        )
        return list((await self.session.scalars(statement)).all())

    async def get_sender_identity(
        self,
        sender_identity_id: int,
    ) -> EmailSenderIdentity | None:
        return await self.session.get(EmailSenderIdentity, sender_identity_id)

    async def get_sender_identity_for_update(
        self,
        sender_identity_id: int,
    ) -> EmailSenderIdentity | None:
        """Lock one sender row for activate/deactivate/delete."""
        statement = (
            select(EmailSenderIdentity)
            .where(EmailSenderIdentity.id == sender_identity_id)
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_sender_identity_by_email(
        self,
        email: str,
    ) -> EmailSenderIdentity | None:
        statement = select(EmailSenderIdentity).where(
            EmailSenderIdentity.email == email.strip().lower()
        )
        return await self.session.scalar(statement)

    async def sender_usage_counts(self) -> dict[int, int]:
        """How many workflow mappings reference each sender identity.

        Both the ``From`` and the Reply-To reference count, and mappings are
        counted whether or not they are enabled, so a deletion cannot orphan a
        stored reference.
        """
        statement = select(
            EmailWorkflowMapping.sender_identity_id,
            EmailWorkflowMapping.reply_to_sender_identity_id,
        )
        counts: dict[int, int] = {}
        for sender_id, reply_to_id in (await self.session.execute(statement)).all():
            for value in (sender_id, reply_to_id):
                if value is not None:
                    counts[value] = counts.get(value, 0) + 1
        return counts

    async def get_mapping(self, mapping_key: str) -> EmailWorkflowMapping | None:
        statement = select(EmailWorkflowMapping).where(
            EmailWorkflowMapping.mapping_key == mapping_key
        )
        return await self.session.scalar(statement)

    # ------------------------------------------------------------------
    # Workflow mappings
    # ------------------------------------------------------------------
    async def list_mappings(self) -> list[EmailWorkflowMapping]:
        statement = select(EmailWorkflowMapping).order_by(
            EmailWorkflowMapping.mapping_key.asc()
        )
        return list((await self.session.scalars(statement)).all())

    async def list_mappings_for_update(self) -> list[EmailWorkflowMapping]:
        """Lock every mapping row for the replacement transaction."""
        statement = (
            select(EmailWorkflowMapping)
            .order_by(EmailWorkflowMapping.mapping_key.asc())
            .with_for_update()
        )
        return list((await self.session.scalars(statement)).all())

    # ------------------------------------------------------------------
    # Internal notification recipients
    # ------------------------------------------------------------------
    async def list_recipients(self) -> list[EmailNotificationRecipient]:
        statement = select(EmailNotificationRecipient).order_by(
            EmailNotificationRecipient.mapping_key.asc(),
            EmailNotificationRecipient.email.asc(),
        )
        return list((await self.session.scalars(statement)).all())

    async def get_recipient(
        self,
        recipient_id: int,
    ) -> EmailNotificationRecipient | None:
        return await self.session.get(EmailNotificationRecipient, recipient_id)

    async def get_recipient_for_update(
        self,
        recipient_id: int,
    ) -> EmailNotificationRecipient | None:
        """Lock one recipient row for edit/activate/delete."""
        statement = (
            select(EmailNotificationRecipient)
            .where(EmailNotificationRecipient.id == recipient_id)
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def list_active_recipients_for_keys(
        self,
        mapping_keys: Sequence[str],
    ) -> list[EmailNotificationRecipient]:
        """Active recipients attached to any of the given scoped workflow keys."""
        keys = tuple(mapping_keys)
        if not keys:
            return []
        statement = (
            select(EmailNotificationRecipient)
            .where(
                EmailNotificationRecipient.mapping_key.in_(keys),
                EmailNotificationRecipient.is_active.is_(True),
            )
            .order_by(EmailNotificationRecipient.email.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_recipient_by_key_email(
        self,
        mapping_key: str,
        email: str,
    ) -> EmailNotificationRecipient | None:
        statement = select(EmailNotificationRecipient).where(
            EmailNotificationRecipient.mapping_key == mapping_key,
            EmailNotificationRecipient.email == email.strip().lower(),
        )
        return await self.session.scalar(statement)

    def add(
        self,
        instance: (
            EmailSmtpProfile
            | EmailSenderIdentity
            | EmailWorkflowMapping
            | EmailNotificationRecipient
        ),
    ) -> None:
        self.session.add(instance)

    async def delete(
        self,
        instance: (
            EmailSmtpProfile
            | EmailSenderIdentity
            | EmailWorkflowMapping
            | EmailNotificationRecipient
        ),
    ) -> None:
        await self.session.delete(instance)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(
        self,
        instance: (
            EmailSmtpProfile
            | EmailSenderIdentity
            | EmailWorkflowMapping
            | EmailNotificationRecipient
        ),
    ) -> None:
        await self.session.refresh(instance)
