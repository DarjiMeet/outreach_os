from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.research_repository import ResearchRepository
from app.schemas.research import (
    CompanyResearchCreate,
    CompanyResearchResponse,
)
from app.services.research_service import ResearchService
from app.api.dependencies import get_research_service


router = APIRouter(
    prefix="/api/v1/research",
    tags=["research"],
)


@router.post(
    "/company",
    response_model=CompanyResearchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def research_company(
    payload: CompanyResearchCreate,
    service: ResearchService = Depends(get_research_service),
):

    return await service.create_company_research(payload)