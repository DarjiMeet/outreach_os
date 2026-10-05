import asyncio
import logging
from urllib.parse import urlparse

from app.config import settings
from app.providers.base import CompanyDiscoveryProvider
from app.schemas.company_discovery import (
    CompanyCandidate, CompanyDiscoveryRequest, CompanyDiscoveryResponse, DiscoverySummary,
)
from app.services.candidate_classifier import CandidateClassifier
from app.services.company_deduplicator import CompanyDeduplicator
from app.services.company_identity import name_key, public_root, is_directory
from app.services.website_resolver import WebsiteResolver

logger = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(
        self, provider: CompanyDiscoveryProvider, classifier: CandidateClassifier,
        deduplicator: CompanyDeduplicator, website_resolver: WebsiteResolver,
    ):
        self.provider = provider
        self.classifier = classifier
        self.deduplicator = deduplicator
        self.website_resolver = website_resolver

    async def discover_companies(self, criteria: CompanyDiscoveryRequest) -> CompanyDiscoveryResponse:
        companies = []
        unresolved = {}
        seen_sources = set()
        attempted = set()
        accepted_names = set()
        accepted_hosts = set()
        excluded_names = []
        warnings = []
        rounds = 0
        stop_reason = "search_round_limit"

        async def resolve(company):
            original_name = company.company_name
            try:
                resolved = await self.website_resolver.resolve_one(company)
                return original_name, resolved, None
            except Exception:
                logger.exception("Website resolution failed for %s", original_name)
                return original_name, company.model_copy(update={"official_website": None}), "resolution_error"

        async def collect(candidates):
            # Consume completions immediately so a later timeout retains earlier successes.
            tasks = [asyncio.create_task(resolve(company)) for company in candidates]
            try:
                for future in asyncio.as_completed(tasks):
                    original_name, company, error = await future
                    root = public_root(company.official_website)
                    key = name_key(company.company_name)
                    if not root or is_directory(root):
                        if key not in accepted_names:
                            unresolved[key] = {
                                "company_name": company.company_name, "source": company.source_url,
                                "reason": error or company._website_failure_reason or "official_website_not_found",
                                "diagnostics": company._website_diagnostics,
                            }
                        if error:
                            warnings.append("A website resolution request failed.")
                        continue
                    host = urlparse(root).hostname.removeprefix("www.")
                    unresolved.pop(name_key(original_name), None)
                    unresolved.pop(key, None)
                    if key in accepted_names or host in accepted_hosts:
                        continue
                    accepted_names.add(key)
                    accepted_hosts.add(host)
                    companies.append(CompanyCandidate(
                        company_name=company.company_name, website=root,
                        location=company.location, description=company.description,
                        source=company.source_url, website_source=company.website_source,
                    ))
                    if len(companies) >= criteria.limit:
                        return
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        try:
            async with asyncio.timeout(settings.discovery_timeout_seconds):
                for round_index in range(settings.discovery_max_rounds):
                    rounds += 1
                    raw_results = await self.provider.search_companies(
                        criteria, round_index=round_index,
                        excluded_companies=tuple(excluded_names),
                    )
                    fresh = [result for result in raw_results if result.url not in seen_sources]
                    seen_sources.update(result.url for result in fresh)
                    # Smaller extraction batches preserve evidence while bounding model input.
                    for offset in range(0, len(fresh), 10):
                        batch = fresh[offset:offset + 10]
                        extraction_criteria = criteria.model_copy(update={
                            "limit": min(100, max(10, (criteria.limit - len(companies)) * 3)),
                        })
                        try:
                            extraction = await self.classifier.classify(batch, extraction_criteria)
                        except Exception as exc:
                            logger.exception("Company extraction failed")
                            # Expose error classification, never response bodies or credentials.
                            status_code = getattr(exc, "status_code", None)
                            detail = type(exc).__name__
                            if isinstance(status_code, int):
                                detail += f", HTTP {status_code}"
                            warnings.append(f"Company extraction failed ({detail}); results may be incomplete.")
                            continue
                        source_urls = {result.url for result in batch}
                        candidates = []
                        for company in self.deduplicator.deduplicate(extraction.companies):
                            key = name_key(company.company_name)
                            identity = (key, company.source_url)
                            if identity in attempted or key in accepted_names:
                                continue
                            attempted.add(identity)
                            excluded_names.append(company.company_name)
                            if company.source_url not in source_urls or company.confidence < 0.7:
                                continue
                            if (
                                criteria.employee_min is not None or criteria.employee_max is not None
                            ) and company.matches_employee_range is not True:
                                continue
                            candidates.append(company)
                        # Limit only after resolution; unresolved names do not consume quota.
                        for start in range(0, len(candidates), 4):
                            await collect(candidates[start:start + 4])
                            if len(companies) >= criteria.limit:
                                break
                        if len(companies) >= criteria.limit:
                            break
                    if len(companies) >= criteria.limit:
                        stop_reason = "target_reached"
                        break
        except TimeoutError:
            stop_reason = "time_budget_exhausted"
            warnings.append("The discovery time budget was reached; partial results are retained.")

        warnings.extend(getattr(self.provider, "warnings", []))
        found = len(companies)
        shortfall = max(0, criteria.limit - found)
        status = "fulfilled" if not shortfall else ("partial" if found else "no_results")
        message = (
            f"Found {found} companies with official websites matching your requirements."
            if not shortfall else
            f"Found {found} of {criteria.limit} requested companies with official websites "
            "matching your requirements within the search budget."
        )
        return CompanyDiscoveryResponse(
            companies=companies,
            discovery_summary=DiscoverySummary(
                requested_count=criteria.limit, found_count=found, shortfall=shortfall,
                status=status, message=message, search_rounds=rounds,
                stop_reason=stop_reason, warnings=list(dict.fromkeys(warnings)),
            ),
            unresolved_companies=list(unresolved.values()),
        )
