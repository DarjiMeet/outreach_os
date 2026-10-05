import asyncio

from app.providers.tavily_provider import TavilyDiscoveryProvider
from app.schemas.company_discovery import ExtractedCompany

class WebsiteResolver:
    def __init__(
        self,
        provider: TavilyDiscoveryProvider
    ):
        self.provider = provider
        self._semaphore = asyncio.Semaphore(4)

    async def resolve_one(
        self,
        company: ExtractedCompany,
    ) -> ExtractedCompany:

        diagnostics = []
        match = await self.provider.resolve_website(
            company_name=company.company_name,
            location=company.location,
            source_url=company.source_url,
            official_website=company.official_website,
            diagnostics=diagnostics,
        )

        company.official_website = match.website if match else None
        company.website_source = match.source_url if match else None
        company._website_diagnostics = diagnostics
        company._website_failure_reason = None
        if match:
            company.company_name = match.company_name
        else:
            codes = {item["code"] for item in diagnostics}
            if codes & {"candidate_identity_mismatch", "candidate_unreadable", "candidate_domain_mismatch"}:
                company._website_failure_reason = "website_verification_failed"
            elif "search_failed" in codes:
                company._website_failure_reason = "website_lookup_incomplete"
            else:
                company._website_failure_reason = "official_website_not_found"

        return company

    async def resolve_many(
        self,
        companies: list[ExtractedCompany],
    ) -> list[ExtractedCompany]:

        async def resolve(company):
            async with self._semaphore:
                return await self.resolve_one(company)

        return await asyncio.gather(*(resolve(company) for company in companies))
