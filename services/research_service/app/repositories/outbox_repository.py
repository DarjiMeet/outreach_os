import json
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outbox_event import OutboxEvent
from datetime import datetime, timedelta, timezone
from sqlalchemy import update


class OutboxRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def add_research_requested_event(
        self,
        research_id: UUID,
        company_url: str,
    ) -> OutboxEvent:

        event = OutboxEvent(
            event_type="research.company.requested",
            aggregate_id=research_id,
            payload=json.dumps(
                {
                    "research_id": str(research_id),
                    "company_url": company_url,
                }
            ),
        )

        self.db.add(event)

        return event

    async def claim_pending(
        self,
        limit: int = 100,
    ) -> list[OutboxEvent]:
        result = await self.db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        events = list(result.scalars().all())

        now = datetime.now(timezone.utc)

        for event in events:
            event.status = "processing"
            event.claimed_at = now

        await self.db.commit()

        return events


    async def mark_published(
        self,
        event: OutboxEvent,
    ) -> None:
        event.status = "published"
        event.published_at = datetime.now(timezone.utc)
        event.claimed_at = None
        await self.db.commit()


    async def mark_pending(
    self,
    event: OutboxEvent,
    ) -> None:

        event.status = "pending"
        event.claimed_at = None

        await self.db.commit()

    async def recover_stale_claims(
        self,
        stale_after_seconds: int = 300,
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=stale_after_seconds
        )

        result = await self.db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == "processing",
                OutboxEvent.claimed_at < cutoff,
            )
            .values(
                status="pending",
                claimed_at=None,
            )
        )

        await self.db.commit()

        return result.rowcount