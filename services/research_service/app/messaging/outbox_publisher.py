import asyncio
import logging

import aio_pika

from app.config import settings
from app.database import AsyncSessionLocal
from app.messaging.constants import RESEARCH_ROUTING_KEY
from app.messaging.topology import setup_research_topology
from app.repositories.outbox_repository import OutboxRepository


POLL_INTERVAL_SECONDS = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("outbox_publisher")


async def publish_pending_events(
    channel,
    exchange,
):
    async with AsyncSessionLocal() as db:
        repository = OutboxRepository(db)

        recovered = await repository.recover_stale_claims()

        if recovered:
            logger.warning("Recovered %s stale outbox events", recovered)

        events = await repository.claim_pending()

        if events:
            logger.info("Claimed %s pending outbox event(s)", len(events))

        for event in events:
            try:
                logger.info(
                    "Publishing event event_id=%s research_id=%s",
                    event.id,
                    event.aggregate_id,
                )
                await exchange.publish(
                    aio_pika.Message(
                        body=event.payload.encode(),
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        message_id=str(event.id),
                    ),
                    routing_key=RESEARCH_ROUTING_KEY,
                    mandatory=True,
                )

                await repository.mark_published(event)

                logger.info("Published event event_id=%s", event.id)

            except Exception as exc:
                await repository.mark_pending(event)

                logger.exception(
                    "Failed to publish event event_id=%s error=%s",
                    event.id,
                    exc,
                )


async def main() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, heartbeat=60)

    async with connection:
        channel = await connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )
        research_exchange, _ = await setup_research_topology(channel)

        logger.info(
            "Outbox publisher running poll_interval_seconds=%s",
            POLL_INTERVAL_SECONDS,
        )

        while True:
            try:
                await publish_pending_events(channel,research_exchange)
            except Exception:
                logger.exception("Outbox polling cycle failed")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
