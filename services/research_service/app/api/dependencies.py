from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.research_repository import ResearchRepository
from app.services.research_service import ResearchService


def get_research_service(
    db: AsyncSession = Depends(get_db),
) -> ResearchService:

    research_repository = ResearchRepository(db)
    outbox_repository = OutboxRepository(db)

    return ResearchService(
        db=db,
        repository=research_repository,
        outbox_repository=outbox_repository,
    )
