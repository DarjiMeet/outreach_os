from pydantic import (
    BaseModel,
    Field,
)


class LeadGenerationRequest(
    BaseModel
):
    query: str | None = None
    industry: str | None = None

    location: str | None = None

    keywords: list[str] = Field(
        default_factory=list
    )

    employee_min: int | None = Field(
        default=None,
        ge=1,
    )

    employee_max: int | None = Field(
        default=None,
        ge=1,
    )

    limit: int = Field(
        default=3,
        ge=1,
        le=100,
    )
