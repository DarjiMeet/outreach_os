from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.research_repository import ResearchRepository
from app.services.research_service import ResearchService


def get_research_repository(
    db: AsyncSession = Depends(get_db),
) -> ResearchRepository:
    return ResearchRepository(db)


def get_research_service(
    repository: ResearchRepository = Depends(get_research_repository),
) -> ResearchService:
    return ResearchService(repository)