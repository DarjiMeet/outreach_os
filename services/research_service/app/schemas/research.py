from uuid import UUID

from pydantic import BaseModel, HttpUrl
from datetime import datetime

class CompanyResearchCreate(BaseModel):
    company_name: str
    company_url: HttpUrl

class CompanyResearchResponse(BaseModel):
    id: UUID
    company_name: str
    company_url: str
    summary: str | None
    extracted_text: str | None
    status: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True  
    }
