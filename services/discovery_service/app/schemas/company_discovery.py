from pydantic import BaseModel, Field, PrivateAttr


class CompanyDiscoveryRequest(BaseModel):
    query: str | None = None
    industry: str | None = None
    location: str | None = None

    employee_min: int | None = Field(
        default=None,
        ge=1,
    )

    employee_max: int | None = Field(
        default=None,
        ge=1,
    )

    keywords: list[str] = Field(
        default_factory=list
    )

    limit: int = Field(
        default=3,
        ge=1,
        le=100,
    )


class RawSearchResult(BaseModel):
    title: str
    url: str
    content: str | None = None


class ExtractedCompany(BaseModel):
    # Runtime diagnostics are not requested from the classifier or included in its schema.
    _website_diagnostics: list[dict] = PrivateAttr(default_factory=list)
    _website_failure_reason: str | None = PrivateAttr(default=None)
    company_name: str
    official_website: str | None = None
    source_url: str
    website_source: str | None = None

    location: str | None = None
    industry: str | None = None
    employee_count: str | None = None
    matches_employee_range: bool | None = None
    description: str | None = None

    confidence: float = Field(
        ge=0,
        le=1,
    )


class CompanyExtractionResponse(BaseModel):
    companies: list[ExtractedCompany]


class CompanyCandidate(BaseModel):
    company_name: str
    website: str | None = None
    location: str | None = None
    description: str | None = None
    source: str
    website_source: str | None = None


class DiscoverySummary(BaseModel):
    requested_count: int
    found_count: int
    shortfall: int
    status: str
    message: str
    search_rounds: int
    stop_reason: str
    warnings: list[str] = Field(default_factory=list)


class CompanyDiscoveryResponse(BaseModel):
    companies: list[CompanyCandidate]
    discovery_summary: DiscoverySummary
    unresolved_companies: list[dict] = Field(default_factory=list)


class ResearchSubmissionResponse(BaseModel):
    jobs: list[dict]
