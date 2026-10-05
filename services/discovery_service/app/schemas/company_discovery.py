from pydantic import BaseModel, Field, PrivateAttr
from typing import Literal


GTMField = Literal[
    "business_overview",
    "products_services",
    "target_customers",
    "business_model",
    "industry",
    "location",
    "employee_range",
    "use_cases",
    "technologies",
    "business_signals",
]

GTM_FIELDS = (
    "business_overview",
    "products_services",
    "target_customers",
    "business_model",
    "industry",
    "location",
    "employee_range",
    "use_cases",
    "technologies",
    "business_signals",
)


class GTMFact(BaseModel):
    field: GTMField

    value: str = Field(
        min_length=1,
        max_length=350,
    )

    source_url: str

    # A short, exact excerpt from the supplied search evidence.
    evidence: str = Field(
        min_length=12,
        max_length=300,
    )

    # For business signals, only populate an explicitly stated date.
    observed_date: str | None = None


class GTMSummary(BaseModel):
    facts: list[GTMFact] = Field(
        default_factory=list,
        max_length=12,
    )

    unknown_fields: list[GTMField] = Field(
        default_factory=list,
        max_length=10,
    )

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

    gtm_summary: GTMSummary = Field(
        default_factory=GTMSummary
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
    gtm_summary: GTMSummary = Field(
        default_factory=GTMSummary
    )



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


