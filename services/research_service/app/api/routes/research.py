from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.research_repository import ResearchRepository
from app.schemas.research import (
    CompanyResearchCreate,
    CompanyResearchResponse,
)
from app.schemas.research_result import ResearchResultResponse
from app.services.research_service import ResearchService
from app.api.dependencies import get_research_service


router = APIRouter(
    prefix="/api/v1/research",
    tags=["research"],
)


@router.post(
    "/company",
    response_model=CompanyResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def research_company(
    payload: CompanyResearchCreate,
    service: ResearchService = Depends(get_research_service),
):

    return await service.create_company_research(payload)


@router.get(
    "/company/{research_id}",
    response_model=CompanyResearchResponse,
)
async def get_company_research(
    research_id: UUID,
    service: ResearchService = Depends(get_research_service),
):
    return await service.get_company_research(research_id)


@router.get(
    "/company/{research_id}/result",
    response_model=ResearchResultResponse | None,
)
async def get_company_research_result(
    research_id: UUID,
    service: ResearchService = Depends(
        get_research_service
    ),
):
    return await service.get_research_result(
        research_id
    )
