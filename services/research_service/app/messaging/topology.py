import aio_pika

from app.messaging.constants import (
    RESEARCH_DLX,
    RESEARCH_DLQ,
    RESEARCH_DLQ_ROUTING_KEY,
    RESEARCH_EXCHANGE,
    RESEARCH_QUEUE,
    RESEARCH_RETRY_QUEUE,
    RESEARCH_ROUTING_KEY,
    RETRY_DELAY_MS,
)


async def setup_research_topology(
    channel: aio_pika.abc.AbstractChannel,
):
    research_exchange = await channel.declare_exchange(
        RESEARCH_EXCHANGE,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    dead_letter_exchange = await channel.declare_exchange(
        RESEARCH_DLX,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    main_queue = await channel.declare_queue(
        RESEARCH_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": RESEARCH_DLX,
            "x-dead-letter-routing-key": RESEARCH_DLQ_ROUTING_KEY,
        },
    )

    await main_queue.bind(
        research_exchange,
        routing_key=RESEARCH_ROUTING_KEY,
    )

    retry_queue = await channel.declare_queue(
        RESEARCH_RETRY_QUEUE,
        durable=True,
        arguments={
            "x-message-ttl": RETRY_DELAY_MS,
            "x-dead-letter-exchange": RESEARCH_EXCHANGE,
            "x-dead-letter-routing-key": RESEARCH_ROUTING_KEY,
        },
    )

    dlq = await channel.declare_queue(
        RESEARCH_DLQ,
        durable=True,
    )

    await dlq.bind(
        dead_letter_exchange,
        routing_key=RESEARCH_DLQ_ROUTING_KEY,
    )

    return research_exchange, retry_queue