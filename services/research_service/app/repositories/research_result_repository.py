from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_result import ResearchResult
from app.schemas.research_result import StructuredResearchResult
from sqlalchemy import select

class ResearchResultRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        research_id: UUID,
        result: StructuredResearchResult,
        extracted_text: str,
    ) -> ResearchResult:

        research_result = ResearchResult(
            research_id=research_id,
            company_name=result.company_name,
            summary=result.summary,
            industry=result.industry,
            products_services=result.products_services,
            technologies=result.technologies,
            locations=result.locations,
            source_urls=result.source_urls,
            extracted_text=extracted_text,
        )

        self.db.add(research_result)

        await self.db.flush()

        return research_result

    async def get_by_researchid(
        self,
        research_id: UUID
    )->ResearchResult | None:

        result = await self.db.execute(
            select(ResearchResult).where(
                ResearchResult.research_id == research_id
            )
        )

        return result.scalar_one_or_none()