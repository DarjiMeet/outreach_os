from uuid import UUID

from pydantic import BaseModel, HttpUrl
from datetime import datetime

class CompanyResearchCreate(BaseModel):
    compaany_name: str
    company_url: HttpUrl

class CompanyResearchResponse(BaseModel):
    id: UUID
    company_name: str
    company_url: str
    summary: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }