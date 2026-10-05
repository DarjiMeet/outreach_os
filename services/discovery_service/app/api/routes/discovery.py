from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_discovery_service,
    get_research_submission_service,
)
from app.schemas.company_discovery import (
    CompanyDiscoveryRequest,
    CompanyDiscoveryResponse,
    CompanyCandidate,
)
from app.services.discovery_service import (
    DiscoveryService,
)
from app.services.research_submission_service import (
    ResearchSubmissionService,
)

router = APIRouter(
    prefix="/api/v1/discovery",
    tags=["discovery"],
)


@router.post(
    "/companies",
    response_model=CompanyDiscoveryResponse,
)
async def discover_companies(
    criteria: CompanyDiscoveryRequest,
    service: DiscoveryService = Depends(
        get_discovery_service
    ),
):
    return await service.discover_companies(
        criteria
    )


@router.post("/research")
async def submit_research(
    companies: list[CompanyCandidate],
    service: ResearchSubmissionService = Depends(
        get_research_submission_service
    ),
):
    jobs = await service.submit_many(companies)

    return {
        "jobs": jobs
    }