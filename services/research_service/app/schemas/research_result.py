from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID

class StructuredResearchResult(BaseModel):
    company_name: str
    summary: str | None = None
    industry: str | None = None

    products_services: list[str] = []
    technologies: list[str] = []
    locations: list[str] = []
    source_urls: list[str] = []


class ResearchResultResponse(BaseModel):
    id: UUID
    research_id: UUID
    company_name: str
    summary: str | None
    industry: str | None
    products_services: list[str] | None
    technologies: list[str] | None
    locations: list[str] | None
    source_urls: list[str] | None
    extracted_text: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )