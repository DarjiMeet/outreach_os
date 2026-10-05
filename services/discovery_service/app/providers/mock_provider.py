from app.providers.base import CompanyDiscoveryProvider
from app.schemas.company_discovery import (
    RawSearchResult,
    CompanyDiscoveryRequest,
)


class MockDiscoveryProvider(
    CompanyDiscoveryProvider
):

    async def search_companies(
        self,
        criteria: CompanyDiscoveryRequest,
        *,
        round_index: int = 0,
        excluded_companies: tuple[str, ...] = (),
    ) -> list[RawSearchResult]:

        return [
            RawSearchResult(
                title="Example AI",
                url="https://example.com",
                content="Example AI company. Official website: https://example.com",
            )
        ]
