"""Exercise discovery metadata across graph checkpoints and resume responses."""

import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("DISCOVERY_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("RESEARCH_SERVICE_URL", "http://localhost:8001")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from langgraph.checkpoint.memory import InMemorySaver

from app.api.routes.lead_generation import generate_leads, resume_lead_generation
from app.graphs.lead_generation_graph import LeadGenerationGraph
from app.schemas.lead_generation import LeadGenerationRequest


class DiscoveryReportingTests(unittest.IsolatedAsyncioTestCase):
    async def test_shortfall_survives_interrupt_checkpoint_and_resume(self):
        summary = {
            "requested_count": 10, "found_count": 1, "shortfall": 9, "status": "partial",
            "message": "Found 1 of 10 requested companies with official websites.",
        }
        discovery = AsyncMock()
        discovery.discover.return_value = {
            "companies": [{"company_name": "Entries AI", "website": "https://entries.ai"}],
            "discovery_summary": summary,
            "unresolved_companies": [{"company_name": "Unknown", "reason": "official_website_not_found"}],
        }
        research = AsyncMock()
        research.create_research.return_value = {"id": "job-1"}
        research.get_research.side_effect = [
            {"id": "job-1", "status": "pending"}, {"id": "job-1", "status": "completed"},
        ]
        research.get_research_result.return_value = {"research_id": "job-1", "company_name": "Entries AI"}
        graph = LeadGenerationGraph(discovery, research, InMemorySaver())

        waiting = await generate_leads(LeadGenerationRequest(limit=10, query="AI ERP"), graph)
        self.assertEqual(waiting["status"], "waiting_for_research")
        self.assertEqual(waiting["discovery_summary"], summary)
        self.assertEqual(discovery.discover.await_args.args[0]["query"], "AI ERP")

        completed = await resume_lead_generation(waiting["thread_id"], graph)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["state"]["discovery_summary"], summary)
        self.assertEqual(len(completed["state"]["research_results"]), 1)
        self.assertEqual(completed["state"]["unresolved_companies"][0]["company_name"], "Unknown")
        self.assertEqual(discovery.discover.await_count, 1)

    async def test_default_three_and_empty_results_are_visible(self):
        discovery = AsyncMock()
        discovery.discover.return_value = {
            "companies": [], "discovery_summary": {
                "requested_count": 3, "found_count": 0, "shortfall": 3, "status": "no_results",
            },
        }
        research = AsyncMock()
        graph = LeadGenerationGraph(discovery, research, InMemorySaver())
        result = await generate_leads(LeadGenerationRequest(), graph)
        self.assertEqual(discovery.discover.await_args.args[0]["limit"], 3)
        self.assertEqual(result["state"]["discovery_summary"]["found_count"], 0)
        research.create_research.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
