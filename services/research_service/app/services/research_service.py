from app.models.company_research import CompanyResearch
from app.repositories.research_repository import ResearchRepository
from app.schemas.research import CompanyResearchCreate


class ResearchService:
    def __init__(self, repository: ResearchRepository):
        self.repository = repository

    async def create_company_research(
        self,
        payload: CompanyResearchCreate,
    ) -> CompanyResearch:
        research = await self.repository.create(
            company_name=payload.company_name,
            company_url=str(payload.company_url),
        )

        return research