import json

import aio_pika

from app.config import settings
from app.messaging.constants import RESEARCH_ROUTING_KEY
from app.messaging.topology import setup_research_topology

RESEARCH_QUEUE = "research.company"

class ResearchPublisher:
    async def publish_company_research(
        self,
        research_id: str,
        company_url: str
    )->None:
        connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            heartbeat=60,
        )

        async with connection:
            channel = await connection.channel()

            research_exchnage, _ = await setup_research_topology(
                channel= channel
            )

            payload = {
               "research_id": research_id,
                "company_url": company_url
            }


            await research_exchnage.publish(
                aio_pika.message(
                    body = json.dumps(payload).encode(),
                    content_type = "application/json",
                    delivery_mode = aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=RESEARCH_ROUTING_KEY
            )