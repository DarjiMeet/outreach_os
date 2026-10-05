import aio_pika

from app.messaging.constants import RESEARCH_RETRY_QUEUE

async def publish_research_retry(
    channel,
    body: bytes
):

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=RESEARCH_RETRY_QUEUE,
    )