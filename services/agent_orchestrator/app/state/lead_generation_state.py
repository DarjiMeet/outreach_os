from typing import TypedDict


class LeadGenerationState(TypedDict, total=False):
    query: str | None
    industry: str | None
    location: str | None
    keywords: list[str]
    employee_min: int | None
    employee_max: int | None
    limit: int
    companies: list[dict]
    discovery_summary: dict
    unresolved_companies: list[dict]
    research_jobs: list[dict]
    research_statuses: list[dict]
    research_results: list[dict]
    research_failures: list[dict]
    research_complete: bool
    error: str | None
