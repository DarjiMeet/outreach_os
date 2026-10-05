import asyncio
from typing import Literal
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.graph import (
    StateGraph,
    START,
    END,
)
from langgraph.types import (
    Command,
    interrupt,
)

from app.clients.discovery_client import (
    DiscoveryClient,
)
from app.clients.research_client import (
    ResearchClient,
)
from app.state.lead_generation_state import (
    LeadGenerationState,
)
from app.utils.url_utils import clean_url


class LeadGenerationGraph:

    def __init__(
        self,
        discovery_client: DiscoveryClient,
        research_client: ResearchClient,
        checkpointer: BaseCheckpointSaver,
    ):
        self.discovery_client = discovery_client
        self.research_client = research_client

        self.checkpointer = checkpointer

        self.graph = self._build_graph()

    @staticmethod
    def _config(thread_id:str)->dict:
        return {
            "configurable": {
                "thread_id": thread_id
            }
        }

    async def discover_companies_node(
        self,
        state: LeadGenerationState,
    ) -> dict:

        criteria = {
            "query": state.get("query"),
            "industry": state.get(
                "industry"
            ),
            "location": state.get(
                "location"
            ),
            "keywords": state.get(
                "keywords",
                [],
            ),
            "employee_min": state.get(
                "employee_min"
            ),
            "employee_max": state.get(
                "employee_max"
            ),
            "limit": state.get(
                "limit",
                3,
            ),
        }

        response = (
            await self.discovery_client.discover(
                criteria
            )
        )

        return {
            "companies": response.get(
                "companies",
                [],
            ),
            "discovery_summary": response.get("discovery_summary", {}),
            "unresolved_companies": response.get("unresolved_companies", []),
        }

    async def research_companies_node(
        self,
        state: LeadGenerationState,
    ) -> dict:

        companies = state.get(
            "companies",
            [],
        )

        tasks = []

        task_companies = []

        for company in companies:

            website = clean_url(
                company.get("website")
            )

            if not website:
                continue

            task_companies.append(
                company
            )

            tasks.append(
                self.research_client.create_research(
                    company_name=company[
                        "company_name"
                    ],
                    company_url=website,
                )
            )

        if not tasks:
            return {
                "research_jobs": [],
                "research_failures": [],
                "research_complete": True,
            }

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        jobs = []
        failures = []

        for company, result in zip(
            task_companies,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):
                failures.append(
                    {
                        "company_name": (
                            company.get(
                                "company_name"
                            )
                        ),
                        "website": company.get(
                            "website"
                        ),
                        "error": str(result),
                    }
                )

                continue

            jobs.append(result)

        return {
            "research_jobs": jobs,
            "research_failures": failures,
            "research_complete": (
                len(jobs) == 0
            ),
        }

    async def check_research_status_node(
        self,
        state: LeadGenerationState,
    ) -> dict:

        jobs = state.get(
            "research_jobs",
            [],
        )

        if not jobs:
            return {
                "research_statuses": [],
                "research_complete": True,
            }

        tasks = [
            self.research_client.get_research(
                job["id"]
            )
            for job in jobs
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        statuses = []

        failures = list(
            state.get(
                "research_failures",
                [],
            )
        )

        for job, result in zip(
            jobs,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):
                failures.append(
                    {
                        "research_id": (
                            job.get("id")
                        ),
                        "company_name": (
                            job.get(
                                "company_name"
                            )
                        ),
                        "error": str(result),
                    }
                )

                continue

            statuses.append(result)

        finished_statuses = {
            "completed",
            "failed",
        }

        all_finished = (
            len(statuses) > 0
            and all(
                status.get(
                    "status",
                    "",
                ).lower()
                in finished_statuses
                for status in statuses
            )
        )

        return {
            "research_statuses": statuses,
            "research_failures": failures,
            "research_complete": all_finished,
        }

    def route_after_status_check(
        self,
        state: LeadGenerationState,
    ) -> Literal["complete", "pending"]:

        if state.get("research_complete", False):
            return "complete"

        return "pending"


    async def collect_research_results_node(
        self,
        state: LeadGenerationState,
    ) -> dict:

        statuses = state.get(
            "research_statuses",
            [],
        )

        completed = [
            status
            for status in statuses
            if status.get(
                "status",
                "",
            ).lower()
            == "completed"
        ]

        if not completed:
            return {
                "research_results": []
            }

        tasks = [
            (
                self.research_client
                .get_research_result(
                    status["id"]
                )
            )
            for status in completed
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        research_results = []

        failures = list(
            state.get(
                "research_failures",
                [],
            )
        )

        for status, result in zip(
            completed,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):
                failures.append(
                    {
                        "research_id": (
                            status.get("id")
                        ),
                        "company_name": (
                            status.get(
                                "company_name"
                            )
                        ),
                        "error": str(result),
                    }
                )

                continue

            research_results.append(
                result
            )

        return {
            "research_results": (
                research_results
            ),
            "research_failures": failures,
        }

    async def wait_for_research_node(self, state: LeadGenerationState) -> dict:

        interrupt(
            {
                "type": "research_pending",
                "message": "Research jobs are still running."
            }
        )

        return {}


    def _build_graph(self):

        builder = StateGraph(
            LeadGenerationState
        )

        builder.add_node(
            "discover_companies",
            self.discover_companies_node,
        )

        builder.add_node(
            "research_companies",
            self.research_companies_node,
        )

        builder.add_node(
            "check_research_status",
            self.check_research_status_node,
        )

        builder.add_node(
            "wait_for_research",
            self.wait_for_research_node,
        )

        builder.add_node(
            "collect_research_results",
            self.collect_research_results_node,
        )

        builder.add_edge(
            START,
            "discover_companies",
        )

        builder.add_edge(
            "discover_companies",
            "research_companies",
        )

        builder.add_edge(
            "research_companies",
            "check_research_status",
        )

        builder.add_conditional_edges(
            "check_research_status",
            self.route_after_status_check,
            {
                "complete": (
                    "collect_research_results"
                ),
                "pending": (
                    "wait_for_research"
                ),
            },
        )

        builder.add_edge(
            "wait_for_research",
            "check_research_status",
        )

        builder.add_edge(
            "collect_research_results",
            END,
        )

        return builder.compile(
            checkpointer=self.checkpointer
        )

    async def run(
        self,
        initial_state: LeadGenerationState,
        thread_id: str,
    ):

        return await self.graph.ainvoke(
            initial_state,
            config=self._config(
                thread_id
            ),
        )

    async def resume(
        self,
        thread_id: str,
    ):

        return await self.graph.ainvoke(
            Command(
                resume=True
            ),
            config=self._config(
                thread_id
            ),
        )

    async def get_state(
        self,
        thread_id: str,
    ) -> dict:

        snapshot = await self.graph.aget_state(
            self._config(
                thread_id
            )
        )

        return dict(
            snapshot.values
        )
