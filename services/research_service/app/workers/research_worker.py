import asyncio
import json
import logging
from uuid import UUID

import aio_pika

from app.analyzers.company_analyzer import CompanyAnalyzer
from app.clients.website_client import WebsiteClient
from app.config import settings
from app.crawlers.company_crawler import CompanyCrawler
from app.database import AsyncSessionLocal
from app.exceptions.analyzer import CompanyAnalysisError
from app.exceptions.website import (
    WebsiteBlockedError,
    WebsiteNotFoundError,
    WebsiteTemporaryError,
)
from app.extractors.website_text_extractor import (
    WebsiteTextExtractor,
)
from app.messaging.constants import MAX_RESEARCH_ATTEMPTS, RESEARCH_QUEUE
from app.messaging.retry_publisher import publish_research_retry
from app.messaging.topology import setup_research_topology
from app.repositories.research_repository import ResearchRepository
from app.repositories.research_result_repository import ResearchResultRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("research_worker")

async def process_research(message: aio_pika.IncomingMessage, channel):

        payload = json.loads(
            message.body.decode()
        )

        research_id = UUID(
            payload["research_id"]
        )

        company_url = payload[
            "company_url"
        ]

        logger.info(
            "Received research job research_id=%s company_url=%s",
            research_id,
            company_url,
        )

        async with AsyncSessionLocal() as db:

            repository = ResearchRepository(db)
            result_repository = ResearchResultRepository(db)

            research = await repository.claim_job(
                research_id
            )

            if research is None:
                logger.info("Skipping duplicate job research_id=%s", research_id)
                await message.ack()
                return

            logger.info(
                "Claimed job research_id=%s attempt=%s",
                research_id,
                research.attempt_count,
            )
            
            try:
                await repository.mark_processing(
                    research
                )

                website_client = WebsiteClient()

                extractor = WebsiteTextExtractor()

                try:
                    crawler = CompanyCrawler(
                        website_client=website_client,
                        text_extractor=extractor,
                    )

                    logger.info("Crawling website research_id=%s", research_id)
                    crawl_result = await crawler.crawl(company_url)

                    logger.info(
                        "Crawl finished research_id=%s pages=%s text_chars=%s",
                        research_id,
                        len(crawl_result.source_urls),
                        len(crawl_result.text),
                    )

                    analyzer = CompanyAnalyzer()

                    logger.info("Analyzing company research_id=%s", research_id)
                    structured_result = await analyzer.analyze(
                        company_name=research.company_name,
                        text=crawl_result.text,
                        source_urls=crawl_result.source_urls,
                    )

                    await result_repository.create(
                        research_id=research.id,
                        result=structured_result,
                        extracted_text=crawl_result.text,
                    )

                    await repository.mark_completed(
                        research,
                    )

                    await db.commit()

                    await message.ack()

                    logger.info("Research completed research_id=%s", research_id)

                except (WebsiteBlockedError, WebsiteNotFoundError) as exc:
                    logger.error(
                        "Permanent website failure research_id=%s error=%s",
                        research_id,
                        exc,
                    )
                    await db.rollback()

                    research = await repository.get_by_id(research_id)

                    if research is None:
                        await message.ack()
                        return

                    await repository.mark_failed(
                        research,
                        str(exc),
                    )

                    await db.commit()

                    await message.reject(requeue=False)
            except WebsiteTemporaryError as exc:
                logger.warning(
                    "Temporary website failure research_id=%s error=%s",
                    research_id,
                    exc,
                )
                await db.rollback()

                research = await repository.get_by_id(research_id)

                if research is None:
                    await message.ack()
                    return
                
                error = str(exc)

                if research.attempt_count < MAX_RESEARCH_ATTEMPTS:

                    await repository.mark_retrying(
                        research,
                        error,
                    )

                    await db.commit()

                    await publish_research_retry(
                        channel,
                        message.body,
                    )

                    await message.ack()

                else:
                    await repository.mark_failed(
                        research,
                        error,
                    )

                    await db.commit()

                    await message.reject(
                        requeue=False
                    )
            except CompanyAnalysisError as exc:
                logger.warning(
                    "Company analysis failure research_id=%s error=%s",
                    research_id,
                    exc,
                )
                await db.rollback()

                research = await repository.get_by_id(research_id)

                if research is None:
                    await message.ack()
                    return

                error = str(exc)

                if research.attempt_count < MAX_RESEARCH_ATTEMPTS:
                    await repository.mark_retrying(
                        research,
                        error,
                    )

                    await db.commit()

                    await publish_research_retry(
                        channel,
                        message.body,
                    )

                    await message.ack()
                else:
                    await repository.mark_failed(
                        research,
                        error,
                    )

                    await db.commit()

                    await message.reject(requeue=False)

async def main():

    connection = await aio_pika.connect_robust(
        settings.rabbitmq_url,
        heartbeat=60,
    )

    channel = await connection.channel()

    await channel.set_qos(
        prefetch_count=1
    )

    _, retry_queue = await setup_research_topology(
        channel
    )

    main_queue = await channel.get_queue(
        RESEARCH_QUEUE
    )

    async def handler(message):
        await process_research(
            message=message,
            channel=channel,
        )

    await main_queue.consume(handler)

    logger.info("Research worker waiting for jobs queue=%s", RESEARCH_QUEUE)

    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
