from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_research import CompanyResearch


class ResearchRepository:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def create(
        self,
        company_name: str,
        company_url : str
    )->CompanyResearch:

        research = CompanyResearch(
            company_name = company_name,
            company_url = company_url
        )

        self.db.add(research)

        await self.db.flush()

        return research
    

    async def mark_processing(
        self,
        research: CompanyResearch
    )->CompanyResearch:
        research.status = "Processing"

        await self.db.commit()
        await self.db.refresh(research)

        return research
    

    async def mark_completed(
        self,
        research: CompanyResearch,
    )->CompanyResearch:
        research.status = "Completed"
        research.last_error = None
        await self.db.flush()

        return research
    

    async def mark_failed(
        self,
        research: CompanyResearch,
        error: str
    )->CompanyResearch:
        research.status = "Failed"
        research.last_error = error
        await self.db.flush()

        return research
    

    async def mark_retrying(
    self,
    research: CompanyResearch,
    error: str,
    ) -> CompanyResearch:

        research.status = "retrying"
        research.last_error = error

        await self.db.flush()

        return research


    async def get_by_id(
    self,
    research_id: UUID,
    ) -> CompanyResearch | None:
        result = await self.db.execute(
            select(CompanyResearch).where(
                CompanyResearch.id == research_id
            )
        )

        return result.scalar_one_or_none()


    async def claim_job(
        self,
        research_id: UUID
    )->CompanyResearch:

        result = await self.db.execute(
            update(CompanyResearch)
            .where(
                CompanyResearch.id == research_id,
                CompanyResearch.status.in_(
                    ["pending", "retrying"]
                ),
            )
            .values(
                status="processing",
                attempt_count=CompanyResearch.attempt_count + 1,
            )
            .returning(CompanyResearch)
        )

        await self.db.commit()

        return result.scalar_one_or_none()


