from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.models.company_research import CompanyResearch
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.research_repository import ResearchRepository
from app.repositories.research_result_repository import ResearchResultRepository
from app.schemas.research import CompanyResearchCreate


class ResearchService:
    def __init__(
        self,
        db: AsyncSession,
        repository: ResearchRepository,
        outbox_repository: OutboxRepository,
    ):
        self.db = db
        self.repository = repository
        self.outbox_repository = outbox_repository

    async def create_company_research(
        self,
        payload: CompanyResearchCreate,
    ) -> CompanyResearch:

        company_url = str(payload.company_url)
        try:
            research = await self.repository.create(
                company_name=payload.company_name,
                company_url=company_url,
            )

            self.outbox_repository.add_research_requested_event(
                research_id=research.id,
                company_url=company_url,
            )

            await self.db.commit()
            await self.db.refresh(research)
        except Exception:
            await self.db.rollback()
            raise

        return research

    async def get_company_research(
        self,
        research_id: UUID,
    ) -> CompanyResearch:
        research = await self.repository.get_by_id(research_id)

        if research is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company research not found",
            )

        return research

    async def get_research_result(
        self,
        research_id: UUID,
    ):
        result_repository = ResearchResultRepository(
            self.db
        )

        return await result_repository.get_by_researchid(
            research_id
        )
