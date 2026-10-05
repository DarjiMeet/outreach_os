"""Offline tests for the bounded classifier evidence window."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.setdefault("GROQ_KEY", "test")
os.environ.setdefault("RESEARCH_SERVICE_URL", "http://localhost:8001")

from app.schemas.company_discovery import CompanyDiscoveryRequest, CompanyExtractionResponse, RawSearchResult
from app.services.candidate_classifier import CandidateClassifier, compress_content, validate_gtm_evidence
from app.services.evidence_selector import select_evidence


class SelectionTests(unittest.TestCase):
    def test_late_facts_replace_navigation_within_budget(self):
        content = "Home\nSign in\nPrivacy policy\n" * 200 + (
            "# Cedar Labs\n"
            "Cedar Labs builds inventory software for retailers.\n"
            "Headquartered in Pune, India.\n"
            "Team size: 51-100 employees.\n"
            "Products: warehouse automation and demand forecasting.\n"
            "Subscription pricing: $49 per month.\n"
            "Integrations: Shopify and SAP.\n"
        )
        selected = select_evidence(content)
        self.assertLessEqual(len(selected), 2000)
        for fact in ["Cedar Labs", "Pune", "51-100 employees", "warehouse automation", "$49", "Shopify"]:
            self.assertIn(fact, selected)
        self.assertNotIn("Privacy policy", selected)

    def test_query_relevance_breaks_equal_scores(self):
        content = "# Suppliers\nCedar makes ceramic tiles.\nBirch makes medical equipment."
        selected = compress_content(content, 65, criteria=CompanyDiscoveryRequest(keywords=["medical equipment"]))
        self.assertIn("Birch makes medical equipment", selected)
        self.assertNotIn("Cedar", selected)

    def test_table_rows_keep_headers_links_and_continuations(self):
        content = (
            "# Companies\n| Company | Details |\n| --- | --- |\n"
            "| [Cedar](https://cedar.example) | Inventory software |\n"
            "| | Headquartered in Pune. |\n"
            "| [Birch](https://birch.example) | Medical equipment |\n"
        )
        selected = select_evidence(content)
        cedar_block = next(block for block in selected.split("\n[...]\n") if "[Cedar]" in block)
        self.assertIn("| Company | Details |", cedar_block)
        self.assertIn("Headquartered in Pune", cedar_block)
        self.assertNotIn("[Birch]", cedar_block)

    def test_headerless_pipe_line_is_not_lost(self):
        self.assertIn("Cedar", select_evidence("Cedar | 50 employees | Pune"))

    def test_nested_company_heading_stays_attached(self):
        selected = select_evidence("# Cedar\n## Products\n### Platform\n#### Details\nInventory software for retailers.")
        self.assertIn("# Cedar", selected)
        self.assertIn("Inventory software", selected)

    def test_empty_and_small_budgets(self):
        self.assertIsNone(select_evidence(None))
        self.assertIsNone(select_evidence(""))
        for limit in [0, 1, 40, 100, 2000]:
            self.assertLessEqual(len(select_evidence("Cedar offers software. " * 300, limit)), limit)

    def test_plain_long_paragraph_keeps_subject_and_tail_fact(self):
        selected = select_evidence("Cedar builds software. " + "Welcome to our world. " * 180 + "Headquartered in Pune with 75 employees.")
        self.assertIn("Headquartered in Pune with 75 employees.", selected)
        tail = next(block for block in selected.split("\n[...]\n") if "75 employees" in block)
        self.assertIn("Cedar builds software.", tail)

    def test_duplicate_blocks_do_not_waste_budget(self):
        selected = select_evidence("# Cedar\nHeadquartered in Pune.\nHeadquartered in Pune.")
        self.assertEqual(selected.count("Headquartered in Pune."), 1)

    def test_directory_link_menu_is_removed(self):
        selected = select_evidence("[Home](/) [Login](/login) [Help](/help)\nCedar builds software.")
        self.assertNotIn("[Login]", selected)
        self.assertIn("Cedar", selected)

    def test_evidence_must_also_exist_in_original_not_just_repeated_heading(self):
        source = "https://cedar.example"
        extraction = CompanyExtractionResponse.model_validate({"companies": [{
            "company_name": "Cedar", "source_url": source, "confidence": 0.9,
            "gtm_summary": {"facts": [
                {"field": "location", "value": "Pune", "source_url": source, "evidence": "Headquartered in Pune."},
                {"field": "business_overview", "value": "invented join", "source_url": source, "evidence": "# Cedar Headquartered in Pune."},
            ]},
        }]})
        validate_gtm_evidence(extraction, [{"url": source, "title": "Cedar", "content": "# Cedar\nHeadquartered in Pune."}],
            [RawSearchResult(url=source, title="Cedar", content="# Cedar\nOther intervening content.\nHeadquartered in Pune.")])
        facts = extraction.companies[0].gtm_summary.facts
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].field, "location")
        self.assertIn("business_overview", extraction.companies[0].gtm_summary.unknown_fields)


class ClassifierWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_llm_payload_is_bounded_and_keeps_late_facts(self):
        classifier = CandidateClassifier.__new__(CandidateClassifier)
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"companies": []}'))]))
        classifier.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        await classifier.classify([RawSearchResult(title="Cedar", url="https://cedar.example", content="Sign in\n" * 1000 + "# Cedar\nHeadquartered in Pune with 75 employees.")], CompanyDiscoveryRequest())
        payload = json.loads(create.call_args.kwargs["messages"][1]["content"])
        content = payload["results"][0]["content"]
        self.assertLessEqual(len(content), 2000)
        self.assertIn("75 employees", content)
        create.assert_awaited_once()
