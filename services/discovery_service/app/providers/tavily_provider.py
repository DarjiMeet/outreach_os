import asyncio
import logging
import re
from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.config import settings
from app.providers.base import CompanyDiscoveryProvider
from app.schemas.company_discovery import CompanyDiscoveryRequest, RawSearchResult
from app.services.company_identity import (
    brand_name, confirmed_name, domain_matches_company, name_key,
    name_variants, normalize_website, public_root, short_name, website_candidates,
)

logger = logging.getLogger(__name__)
_domain_matches_company = domain_matches_company


def _diagnose(diagnostics: list[dict] | None, code: str, **details) -> None:
    if diagnostics is not None:
        item = {"code": code, **details}
        if item not in diagnostics:
            diagnostics.append(item)


@dataclass
class WebsiteMatch:
    company_name: str
    website: str
    source_url: str


class TavilyDiscoveryProvider(CompanyDiscoveryProvider):
    def __init__(self):
        self.client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        self._requests = asyncio.Semaphore(4)
        self._source_locks: dict[str, asyncio.Lock] = {}
        self._source_content: dict[str, str] = {}
        self._source_failures: dict[str, str] = {}
        self.warnings: list[str] = []

    async def _search(self, query: str, *, diagnostics: list[dict] | None = None, **kwargs) -> list[dict]:
        try:
            async with self._requests:
                response = await self.client.search(
                    query=query, search_depth="advanced", timeout=15,
                    include_raw_content="markdown", **kwargs,
                )
            results = response.get("results", [])
            if not results:
                _diagnose(diagnostics, "search_no_results", query=query)
            for result in results:
                if result.get("url") and result.get("raw_content"):
                    self._source_content[result["url"]] = result["raw_content"]
            return results
        except Exception as exc:
            logger.exception("Discovery search failed")
            self.warnings.append("A search request failed; results may be incomplete.")
            _diagnose(diagnostics, "search_failed", query=query, error_type=type(exc).__name__,
                      status_code=getattr(exc, "status_code", None))
            return []

    def _build_query(self, criteria: CompanyDiscoveryRequest) -> list[str]:
        # Keep every supplied constraint in each query, including free-form query text.
        parts = [criteria.query, criteria.industry, " ".join(criteria.keywords), "companies"]
        if criteria.location:
            parts.append(f"in {criteria.location}")
        if criteria.employee_min is not None and criteria.employee_max is not None:
            parts.append(f"with {criteria.employee_min} to {criteria.employee_max} employees")
        elif criteria.employee_min is not None:
            parts.append(f"with at least {criteria.employee_min} employees")
        elif criteria.employee_max is not None:
            parts.append(f"with at most {criteria.employee_max} employees")
        return [" ".join(part for part in parts if part)]

    async def search_companies(
        self, criteria: CompanyDiscoveryRequest, *, round_index: int = 0,
        excluded_companies: tuple[str, ...] = (),
    ) -> list[RawSearchResult]:
        base = self._build_query(criteria)[0]
        # Different indexed platforms provide new candidates without relaxing criteria.
        suffixes = (
            ("official websites", "startup directory"),
            (
                "site:linkedin.com/company",
                "site:wellfound.com/company",
                "site:ycombinator.com/companies",
            ),
            ("site:clutch.co", "software companies directory alternatives"),
        )[min(round_index, 2)]
        exclusions = " ".join(
            '-"' + name.replace('"', '') + '"' for name in excluded_companies[-10:]
        )
        batches = await asyncio.gather(*[
            self._search(
                f"{base} {suffix} {exclusions}".strip(),
                max_results=min(20, max(5, criteria.limit * 2)),
            ) for suffix in suffixes
        ])
        unique = {}
        for batch in batches:
            for result in batch:
                url = result.get("url")
                if public_root(url):
                    unique[url] = RawSearchResult(
                        title=result.get("title") or "", url=url,
                        content=result.get("raw_content") or result.get("content"),
                    )
        return list(unique.values())

    async def _extract_source(self, url: str, diagnostics: list[dict] | None = None) -> str:
        if not public_root(url):
            return ""
        async with self._source_locks.setdefault(url, asyncio.Lock()):
            if url in self._source_content:
                if not self._source_content[url]:
                    _diagnose(diagnostics, self._source_failures.get(url, "source_unreadable"), url=url)
                return self._source_content[url]
            try:
                async with self._requests:
                    response = await self.client.extract(
                        urls=[url], format="markdown", extract_depth="advanced", timeout=10,
                    )
                content = "\n".join(
                    result.get("raw_content") or "" for result in response.get("results", [])
                )
                if not content:
                    self.warnings.append("A source page could not be read; website fallback search was used.")
                    self._source_failures[url] = "source_unreadable"
                    _diagnose(diagnostics, "source_unreadable", url=url)
            except Exception as exc:
                logger.exception("Could not extract website source")
                self.warnings.append("A source page could not be read; website fallback search was used.")
                self._source_failures[url] = "source_fetch_failed"
                _diagnose(diagnostics, "source_fetch_failed", url=url, error_type=type(exc).__name__,
                          status_code=getattr(exc, "status_code", None))
                content = ""
            self._source_content[url] = content
            return content

    @staticmethod
    def _linked_website(name: str, content: str, source_url: str) -> WebsiteMatch | None:
        # A company-labelled link or explicit Website field is a candidate,
        # not a verified match until resolve_website checks the destination.
        variants = {name_key(variant): variant for variant in name_variants(name)}
        for label, target in re.findall(r"(?<!!)\[([^\]\n]+)\]\(([^)\s]+)(?:\s+[^)]*)?\)", content):
            matched_name = variants.get(name_key(label))
            url = normalize_website(target)
            if matched_name and url and domain_matches_company(matched_name, url):
                return WebsiteMatch(matched_name, url, source_url)

        matched_name = confirmed_name(name, content)
        if matched_name:
            for field in re.finditer(r"\b(?:website|official site)\b", content, flags=re.I):
                # Supports bare domains, Markdown links and button labels after Website.
                nearby = content[field.end():field.end() + 160]
                candidates = website_candidates(matched_name, nearby)
                if candidates:
                    return WebsiteMatch(matched_name, candidates[0], source_url)
        return None

    async def resolve_website(
        self, company_name: str, location: str | None = None,
        source_url: str | None = None, official_website: str | None = None,
        *, diagnostics: list[dict] | None = None,
    ) -> WebsiteMatch | None:
        diagnostics = diagnostics if diagnostics is not None else []
        checked_candidates = set()
        inspected_profiles = set()
        candidate_limit = 5

        async def verify(candidate: WebsiteMatch) -> WebsiteMatch | None:
            url = candidate.website
            if not domain_matches_company(candidate.company_name, url):
                _diagnose(diagnostics, "candidate_domain_mismatch", url=url)
                return None
            # Retry an explicitly observed non-www URL if its www variant was unreadable.
            # Repeated identical URLs are still checked once, within the same total limit.
            key = public_root(url)
            if key in checked_candidates:
                return None
            if len(checked_candidates) >= candidate_limit:
                _diagnose(diagnostics, "candidate_limit_reached")
                return None
            checked_candidates.add(key)
            content = await self._extract_source(url, diagnostics)
            if not content:
                _diagnose(diagnostics, "candidate_unreadable", url=url)
                return None
            canonical = confirmed_name(candidate.company_name, content)
            # Directory display suffixes may be absent from the official page's brand name.
            # The exact domain check above is required before using this shorter form.
            if not canonical:
                brand = brand_name(candidate.company_name)
                if len(name_key(brand)) >= 4 and confirmed_name(brand, content):
                    canonical = candidate.company_name
            if not canonical:
                _diagnose(diagnostics, "candidate_identity_mismatch", url=url)
                return None
            _diagnose(diagnostics, "website_verified", url=url, source_url=candidate.source_url)
            return WebsiteMatch(canonical, url, candidate.source_url)

        async def inspect_text(content: str, evidence_url: str) -> WebsiteMatch | None:
            linked = self._linked_website(company_name, content, evidence_url)
            if linked:
                match = await verify(linked)
                if match:
                    return match
            canonical = confirmed_name(company_name, content)
            if not canonical:
                return None
            # A domain in a relevant snippet/title is useful evidence even if the
            # result itself is an unfamiliar directory or article.
            for url in website_candidates(canonical, content):
                match = await verify(WebsiteMatch(canonical, url, evidence_url))
                if match:
                    return match
            return None

        if source_url:
            content = await self._extract_source(source_url, diagnostics)
            match = await inspect_text(content, source_url)
            if match:
                return match
            canonical = confirmed_name(company_name, content)
            if canonical and domain_matches_company(canonical, source_url):
                match = await verify(WebsiteMatch(canonical, public_root(source_url), source_url))
                if match:
                    return match

        if official_website:
            url = normalize_website(official_website)
            if url:
                match = await verify(WebsiteMatch(company_name, url, official_website))
                if match:
                    return match

        names = list(dict.fromkeys(short_name(name) for name in name_variants(company_name)))
        queries = [f'"{names[0]}" official website {location or ""}'.strip()]
        queries += [f'"{name}" official website' for name in names]
        # An unquoted query is less restrictive when a brand is styled differently.
        queries += [f'{names[-1]} official website',
                    f'"{names[-1]}" {location or ""} site:linkedin.com/company website',
                    f'"{names[-1]}" {location or ""} company profile website']
        for query in dict.fromkeys(queries):
            results = await self._search(query, max_results=5, diagnostics=diagnostics)
            for result in results:
                url = result.get("url") or ""
                if not public_root(url):
                    continue
                evidence = "\n".join(result.get(field) or "" for field in ("title", "content", "raw_content"))
                canonical = confirmed_name(company_name, evidence)
                if not canonical:
                    continue
                if domain_matches_company(canonical, url):
                    match = await verify(WebsiteMatch(canonical, public_root(url), url))
                    if match:
                        return match
                # Try available snippet/raw evidence before spending another extract call.
                match = await inspect_text(evidence, url)
                if match:
                    return match
                if not result.get("raw_content") and url not in inspected_profiles:
                    if len(inspected_profiles) >= 3:
                        _diagnose(diagnostics, "profile_limit_reached")
                        continue
                    inspected_profiles.add(url)
                    # Any relevant source may contain the website; a directory allowlist
                    # must not prevent inspection of CB Insights, Internshala, etc.
                    content = await self._extract_source(url, diagnostics)
                    match = await inspect_text(content, url)
                    if match:
                        return match
        _diagnose(diagnostics, "no_verified_website")
        return None
    async def find_official_website(self, company_name: str, location: str | None = None) -> str | None:
        match = await self.resolve_website(company_name, location)
        return match.website if match else None
