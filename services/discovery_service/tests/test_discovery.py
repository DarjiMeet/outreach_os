"""Offline regressions: noisy source labels, fallback identity, and quota fulfillment."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

# Do not read real credentials or make external requests in this suite.
os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.setdefault("GROQ_KEY", "test")
os.environ.setdefault("RESEARCH_SERVICE_URL", "http://localhost:8001")

from app.config import settings
from app.providers.tavily_provider import TavilyDiscoveryProvider
from app.schemas.company_discovery import (
    CompanyDiscoveryRequest, CompanyExtractionResponse, ExtractedCompany, RawSearchResult,
)
from app.services.candidate_classifier import CandidateClassifier
from app.services.company_deduplicator import CompanyDeduplicator
from app.services.company_identity import (
    confirmed_name, domain_matches_company, name_variants, normalize_website, website_candidates,
)
from app.services.discovery_service import DiscoveryService
from app.services.website_resolver import WebsiteResolver


def company(name, website=None, source="https://directory.example/list", **kwargs):
    return ExtractedCompany(
        company_name=name, official_website=website, source_url=source,
        confidence=0.9, **kwargs,
    )


def provider():
    with patch("app.providers.tavily_provider.AsyncTavilyClient") as client:
        instance = TavilyDiscoveryProvider()
        client.return_value.search = AsyncMock(return_value={"results": []})
        client.return_value.extract = AsyncMock(return_value={"results": []})
    return instance


class WebsiteTests(unittest.IsolatedAsyncioTestCase):
    async def test_directory_logo_initials_are_corrected_from_label_evidence(self):
        p = provider()
        source = "https://revenuebase.ai/companies/list"
        p._source_content[source] = (
            "E [Entries AI](https://entries.ai)\n"
            "C [Chimera Technologies Private Limited](https://www.chimeratechnologies.com)"
        )
        p._source_content["https://entries.ai"] = "Entries AI: AI ERP for businesses"
        p._source_content["https://www.chimeratechnologies.com"] = "Chimera Technologies: software engineering"
        resolver = WebsiteResolver(p)
        results = await resolver.resolve_many([
            company("EEntries AI", source=source),
            company("CChimera Technologies Private Limited", source=source),
        ])
        self.assertEqual([c.company_name for c in results], ["Entries AI", "Chimera Technologies Private Limited"])
        self.assertEqual([c.official_website for c in results], ["https://entries.ai", "https://www.chimeratechnologies.com"])
        p.client.search.assert_not_awaited()

    async def test_real_repeated_letters_are_preserved(self):
        self.assertEqual(name_variants("Aardvark"), ["Aardvark"])
        self.assertEqual(name_variants("AAI"), ["AAI"])
        self.assertIsNone(confirmed_name("EEntries AI", "Other company"))
        self.assertEqual(confirmed_name("EEntries AI", "EEntries AI official"), "EEntries AI")

    async def test_corrected_query_requires_result_name_evidence(self):
        p = provider()
        p._source_content["https://entries.ai"] = "Entries AI: AI ERP for businesses"

        async def search(query, **kwargs):
            if query == '"Entries AI" official website':
                return {"results": [{"url": "https://entries.ai", "title": "Entries AI — ERP"}]}
            return {"results": []}

        p.client.search.side_effect = search
        match = await p.resolve_website("EEntries AI", "Bangalore")
        self.assertEqual(match.company_name, "Entries AI")
        self.assertEqual(match.website, "https://entries.ai")

    async def test_linkedin_fallback_reads_website_field_but_does_not_return_linkedin(self):
        p = provider()
        p._source_content["https://entries.ai"] = "Entries AI: AI ERP for businesses"

        async def search(query, **kwargs):
            if "site:linkedin.com" in query:
                return {"results": [{
                    "url": "https://www.linkedin.com/company/entries-ai/",
                    "title": "Entries AI | LinkedIn",
                    "raw_content": "Entries AI\nWebsite\nhttps://entries.ai",
                }]}
            return {"results": []}

        p.client.search.side_effect = search
        match = await p.resolve_website("Entries AI", "Bangalore")
        self.assertEqual(match.website, "https://entries.ai")
        self.assertIn("linkedin.com", match.source_url)

    async def test_unresolved_profile_is_not_an_official_website(self):
        p = provider()
        p.client.search.return_value = {"results": [{
            "url": "https://linkedin.com/company/entries-ai", "title": "Entries AI",
        }]}
        self.assertIsNone(await p.resolve_website("Entries AI"))

    async def test_weak_similarity_generic_words_and_unsafe_urls_are_rejected(self):
        for url in ["https://technologies.com", "https://chimera-news.com", "https://linkedin.com/company/chimera", "https://chimeratechnologies.unrelated.com", "http://127.0.0.1", "javascript:alert(1)"]:
            self.assertFalse(domain_matches_company("Chimera Technologies", url), url)
        self.assertTrue(domain_matches_company("Chimera Technologies Private Limited", "https://www.chimeratechnologies.com"))
        self.assertTrue(domain_matches_company("Entries AI", "https://www.entries.co.in"))

    async def test_source_extraction_is_shared_by_concurrent_companies(self):
        p = provider()
        async def extract(urls, **kwargs):
            pages = {
                "https://directory.example/list": "[Alpha](https://alpha.example) [Bravo](https://bravo.example)",
                "https://alpha.example": "Alpha official website",
                "https://bravo.example": "Bravo official website",
            }
            return {"results": [{"raw_content": pages[urls[0]]}]}
        p.client.extract.side_effect = extract
        source = "https://directory.example/list"
        matches = await asyncio.gather(
            p.resolve_website("Alpha", source_url=source), p.resolve_website("Bravo", source_url=source),
        )
        self.assertTrue(all(matches))
        calls = [call.kwargs["urls"][0] for call in p.client.extract.await_args_list]
        self.assertEqual(calls.count(source), 1)
        self.assertEqual(len(calls), 3)  # shared directory + two destination checks

    async def test_search_failure_falls_back_and_is_reported(self):
        p = provider()
        p._source_content["https://entries.ai"] = "Entries AI: AI ERP for businesses"
        p.client.search.side_effect = [RuntimeError("offline"), {"results": [{
            "url": "https://entries.ai", "title": "Entries AI",
        }]}]
        match = await p.resolve_website("Entries AI", "Bangalore")
        self.assertEqual(match.website, "https://entries.ai")
        self.assertTrue(p.warnings)

    async def test_bare_domain_and_markdown_website_fields_are_verified(self):
        for field in ["Website\nwww.astiva.ai", "Website: astiva.ai.", "Website [Visit site](//www.astiva.ai)"]:
            with self.subTest(field=field):
                p = provider()
                source = "https://wellfound.com/company/astiva-ai"
                p._source_content[source] = "Astiva AI\n" + field
                p.client.extract.return_value = {"results": [{"raw_content": "Astiva: competitive intelligence for AI search"}]}
                diagnostics = []
                result = await p.resolve_website("Astiva AI", source_url=source, diagnostics=diagnostics)
                self.assertIsNotNone(result)
                self.assertIn(result.website, {"https://astiva.ai", "https://www.astiva.ai"})
                self.assertEqual(result.source_url, source)
                self.assertIn("website_verified", [d["code"] for d in diagnostics])
                p.client.search.assert_not_awaited()

    async def test_domain_in_search_snippet_recovers_unreadable_source(self):
        p = provider()
        p.client.search.return_value = {"results": [{
            "url": "https://inite.ai/en/atlas/astiva.ai/visibility",
            "title": "Astiva AI: how AI assistants read astiva.ai | INITE Atlas",
        }]}
        async def extract(urls, **kwargs):
            if urls == ["https://astiva.ai"]:
                return {"results": [{"raw_content": "Astiva AI helps brands improve AI visibility"}]}
            return {"results": []}
        p.client.extract.side_effect = extract
        diagnostics = []
        result = await p.resolve_website("Astiva AI", source_url="https://wellfound.com/company/astiva-ai", diagnostics=diagnostics)
        self.assertEqual(result.website, "https://astiva.ai")
        self.assertEqual(result.source_url, "https://inite.ai/en/atlas/astiva.ai/visibility")
        self.assertIn("source_unreadable", [d["code"] for d in diagnostics])

    async def test_unlisted_profile_can_supply_a_website(self):
        p = provider()
        profile = "https://new-directory.example/companies/astiva"
        p.client.search.return_value = {"results": [{"url": profile, "title": "Astiva AI company profile"}]}
        async def extract(urls, **kwargs):
            content = "Astiva AI\nWebsite: astiva.ai" if urls == [profile] else "Astiva AI official website"
            return {"results": [{"raw_content": content}]}
        p.client.extract.side_effect = extract
        result = await p.resolve_website("Astiva AI")
        self.assertEqual(result.website, "https://astiva.ai")
        self.assertEqual(result.source_url, profile)

    async def test_non_www_evidence_can_recover_after_www_failure(self):
        p = provider()
        source = "https://wellfound.com/company/astiva-ai"
        p._source_content[source] = "Astiva AI\nWebsite: www.astiva.ai"
        p._source_content["https://astiva.ai"] = "Astiva AI official site"
        p.client.search.return_value = {"results": [{"url": "https://astiva.ai", "title": "Astiva AI"}]}
        result = await p.resolve_website("Astiva AI", source_url=source)
        self.assertEqual(result.website, "https://astiva.ai")

    async def test_matching_domain_without_destination_identity_is_rejected(self):
        p = provider()
        p.client.search.return_value = {"results": [{"url": "https://astiva.ai", "title": "Astiva AI official"}]}
        p.client.extract.return_value = {"results": [{"raw_content": "Domain for sale. Buy this domain today."}]}
        diagnostics = []
        self.assertIsNone(await p.resolve_website("Astiva AI", diagnostics=diagnostics))
        self.assertIn("candidate_identity_mismatch", [d["code"] for d in diagnostics])
        self.assertEqual(sum(call.kwargs["urls"] == ["https://astiva.ai"] for call in p.client.extract.await_args_list), 1)

    async def test_unreadable_candidate_is_reported_on_company(self):
        p = provider()
        source = "https://wellfound.com/company/astiva-ai"
        p._source_content[source] = "Astiva AI\nWebsite: astiva.ai"
        result = await WebsiteResolver(p).resolve_one(company("Astiva AI", source=source))
        self.assertIsNone(result.official_website)
        self.assertEqual(result._website_failure_reason, "website_verification_failed")
        self.assertIn("candidate_unreadable", [d["code"] for d in result._website_diagnostics])

    async def test_prefix_names_no_longer_match_other_businesses(self):
        self.assertFalse(domain_matches_company("Rilo", "https://it.rilogroup.com"))
        self.assertFalse(domain_matches_company("Astiva AI", "https://astivahealth.com"))
        self.assertTrue(domain_matches_company("Astiva AI", "https://astiva.ai"))
        self.assertTrue(domain_matches_company("Spacenos HQ", "https://spacenos.com"))

    async def test_candidate_extraction_rejects_emails_and_misleading_domains(self):
        text = "Contact hello@astiva.ai. Not astiva.ai.evil.com. Official: www.astiva.ai."
        self.assertEqual(website_candidates("Astiva AI", text), ["https://www.astiva.ai"])
        for url in ["javascript:alert(1)", "http://127.0.0.1", "astiva.ai@evil.com", "https://[broken"]:
            self.assertIsNone(normalize_website(url), url)

    async def test_resolution_details_are_not_part_of_classifier_schema(self):
        schema = ExtractedCompany.model_json_schema()
        self.assertNotIn("_website_diagnostics", schema["properties"])
        self.assertNotIn("_website_failure_reason", schema["properties"])

    async def test_queries_keep_constraints_and_cap_tavily_page_size(self):
        p = provider()
        request = CompanyDiscoveryRequest(query="accounting", industry="AI software", location="India", employee_min=10, employee_max=200, limit=100)
        await p.search_companies(request, round_index=1, excluded_companies=("Existing",))
        for call in p.client.search.await_args_list:
            self.assertLessEqual(call.kwargs["max_results"], 20)
            for expected in ["accounting", "AI software", "India", "10 to 200", '-"Existing"']:
                self.assertIn(expected, call.kwargs["query"])
        self.assertIn("site:linkedin.com/company", p.client.search.await_args_list[0].kwargs["query"])


class FulfillmentTests(unittest.IsolatedAsyncioTestCase):
    def service(self, rounds, resolver=None):
        p = provider()
        batches = [
            [RawSearchResult(title="Directory", url=c.source_url) for c in candidates]
            for candidates in rounds
        ]
        p.search_companies = AsyncMock(side_effect=batches + [[]] * 3)
        classifier = AsyncMock()
        classifier.classify.side_effect = [CompanyExtractionResponse(companies=c) for c in rounds]
        if resolver is None:
            resolver = AsyncMock()

            async def resolve(c):
                return c

            resolver.resolve_one.side_effect = resolve
        return DiscoveryService(p, classifier, CompanyDeduplicator(), resolver)

    async def test_unresolved_candidates_do_not_consume_quota(self):
        service = self.service([[
            company("Missing"), company("Alpha", "https://alpha.example"),
            company("Bravo", "https://bravo.example"),
        ]])
        result = await service.discover_companies(CompanyDiscoveryRequest(limit=2))
        self.assertEqual(len(result.companies), 2)
        self.assertEqual(result.discovery_summary.status, "fulfilled")
        self.assertEqual(result.unresolved_companies[0]["company_name"], "Missing")
        self.assertEqual(service.provider.search_companies.await_count, 1)

    async def test_replacement_search_uses_new_sources_and_original_constraints(self):
        service = self.service([
            [company("Missing"), company("Alpha", "https://alpha.example", matches_employee_range=True)],
            [company("Bravo", "https://bravo.example", source="https://other.example/list", matches_employee_range=True)],
        ])
        request = CompanyDiscoveryRequest(limit=2, industry="AI", employee_min=10)
        result = await service.discover_companies(request)
        self.assertEqual(result.discovery_summary.found_count, 2)
        self.assertEqual(result.discovery_summary.search_rounds, 2)
        call = service.provider.search_companies.await_args_list[1]
        self.assertEqual(call.args[0], request)
        self.assertIn("Alpha", call.kwargs["excluded_companies"])

    async def test_exhaustion_reports_actual_count_and_shortfall(self):
        service = self.service([[company("Alpha", "https://alpha.example")]])
        result = await service.discover_companies(CompanyDiscoveryRequest(limit=10))
        self.assertEqual(result.discovery_summary.found_count, 1)
        self.assertEqual(result.discovery_summary.shortfall, 9)
        self.assertEqual(result.discovery_summary.status, "partial")
        self.assertEqual(result.discovery_summary.search_rounds, 3)
        self.assertIn("1 of 10", result.discovery_summary.message)

    async def test_zero_results_and_default_three(self):
        service = self.service([])
        result = await service.discover_companies(CompanyDiscoveryRequest())
        self.assertEqual(result.discovery_summary.requested_count, 3)
        self.assertEqual(result.discovery_summary.status, "no_results")
        self.assertEqual(result.discovery_summary.shortfall, 3)

    async def test_duplicate_names_and_domains_do_not_inflate_count(self):
        service = self.service([[
            company("Alpha Inc", "https://alpha.example"),
            company("Alpha", "https://alpha.example"),
            company("Alpha Brand", "https://www.alpha.example"),
            company("Bravo", "https://bravo.example"),
        ]])
        result = await service.discover_companies(CompanyDiscoveryRequest(limit=3))
        self.assertEqual(result.discovery_summary.found_count, 2)

    async def test_low_confidence_and_employee_mismatch_are_excluded(self):
        candidates = [company("Small", "https://small.example", matches_employee_range=False),
                      company("Unsure", "https://unsure.example", matches_employee_range=True)]
        candidates[1].confidence = 0.4
        service = self.service([candidates])
        result = await service.discover_companies(CompanyDiscoveryRequest(employee_min=10))
        self.assertEqual(result.companies, [])
        service.website_resolver.resolve_one.assert_not_awaited()

    async def test_classifier_cannot_invent_a_discovery_source(self):
        service = self.service([[company("Alpha", "https://alpha.example")]])
        service.classifier.classify.side_effect = [CompanyExtractionResponse(companies=[
            company("Invented", "https://invented.example", source="https://not-searched.example"),
        ])]
        result = await service.discover_companies(CompanyDiscoveryRequest())
        self.assertEqual(result.companies, [])
        service.website_resolver.resolve_one.assert_not_awaited()

    async def test_timeout_retains_already_resolved_companies(self):
        resolver = AsyncMock()

        async def resolve(c):
            if c.company_name == "Slow":
                await asyncio.sleep(10)
            return c

        resolver.resolve_one.side_effect = resolve
        service = self.service([[company("Alpha", "https://alpha.example"), company("Slow")]], resolver)
        with patch.object(settings, "discovery_timeout_seconds", 0.05):
            result = await service.discover_companies(CompanyDiscoveryRequest(limit=3))
        self.assertEqual(result.discovery_summary.found_count, 1)
        self.assertEqual(result.discovery_summary.stop_reason, "time_budget_exhausted")

    async def test_resolution_failure_does_not_discard_other_companies(self):
        resolver = AsyncMock()

        async def resolve(c):
            if c.company_name == "Broken":
                raise RuntimeError("unavailable")
            return c

        resolver.resolve_one.side_effect = resolve
        service = self.service([[company("Broken"), company("Alpha", "https://alpha.example")]], resolver)
        result = await service.discover_companies(CompanyDiscoveryRequest(limit=2))
        self.assertEqual(result.discovery_summary.found_count, 1)
        self.assertTrue(result.discovery_summary.warnings)

    async def test_empty_classifier_input(self):
        classifier = CandidateClassifier.__new__(CandidateClassifier)
        result = await classifier.classify([], CompanyDiscoveryRequest())
        self.assertEqual(result.companies, [])

    async def test_unresolved_response_contains_specific_diagnostics(self):
        p = provider()
        source = "https://wellfound.com/company/astiva-ai"
        p._source_content[source] = "Astiva AI\nWebsite: astiva.ai"
        service = self.service([[company("Astiva AI", source=source)]], WebsiteResolver(p))
        result = await service.discover_companies(CompanyDiscoveryRequest())
        unresolved = result.model_dump()["unresolved_companies"][0]
        self.assertEqual(unresolved["reason"], "website_verification_failed")
        self.assertIn({"code": "candidate_unreadable", "url": "https://astiva.ai"}, unresolved["diagnostics"])

    async def test_extraction_warning_classifies_error_without_leaking_body(self):
        class ExtractionError(Exception):
            status_code = 429

        service = self.service([[company("Alpha", "https://alpha.example")]])
        service.classifier.classify.side_effect = ExtractionError("secret response body")
        result = await service.discover_companies(CompanyDiscoveryRequest())
        warnings = " ".join(result.discovery_summary.warnings)
        self.assertIn("ExtractionError, HTTP 429", warnings)
        self.assertNotIn("secret response body", warnings)


if __name__ == "__main__":
    unittest.main()
