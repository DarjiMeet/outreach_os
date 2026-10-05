from abc import ABC, abstractmethod

from app.schemas.company_discovery import (
    CompanyDiscoveryRequest,
    RawSearchResult,
)


class CompanyDiscoveryProvider(ABC):

    @abstractmethod
    async def search_companies(
        self,
        criteria: CompanyDiscoveryRequest,
        *,
        round_index: int = 0,
        excluded_companies: tuple[str, ...] = (),
    ) -> list[RawSearchResult]:
        raise NotImplementedError
