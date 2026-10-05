import asyncio

from app.clients.research_client import ResearchClient
from app.schemas.company_discovery import CompanyCandidate


class ResearchSubmissionService:
    def __init__(self, research_client: ResearchClient):
        self.research_client = research_client

    async def submit_many(
        self,
        companies: list[CompanyCandidate],
    ) -> list[dict]:

        tasks = []

        for company in companies:
            if not company.website:
                continue

            tasks.append(
                self.research_client.create_research_job(
                    company_name=company.company_name,
                    company_url=company.website,
                )
            )

        if not tasks:
            return []

        return await asyncio.gather(*tasks)