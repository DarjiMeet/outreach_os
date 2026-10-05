from contextlib import (
    asynccontextmanager,
)

from fastapi import FastAPI

from langgraph.checkpoint.redis.aio import (
    AsyncRedisSaver,
)

from app.clients.discovery_client import (
    DiscoveryClient,
)
from app.clients.research_client import (
    ResearchClient,
)
from app.config import settings
from app.graphs.lead_generation_graph import (
    LeadGenerationGraph,
)
from app.api.routes.lead_generation import (
    router as lead_generation_router,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):

    async with (
        AsyncRedisSaver.from_conn_string(
            settings.redis_url
        )
        as checkpointer
    ):

        await checkpointer.asetup()

        discovery_client = (
            DiscoveryClient(
                base_url=(
                    settings
                    .discovery_service_url
                )
            )
        )

        research_client = (
            ResearchClient(
                base_url=(
                    settings
                    .research_service_url
                )
            )
        )

        graph = LeadGenerationGraph(
            discovery_client=(
                discovery_client
            ),
            research_client=(
                research_client
            ),
            checkpointer=checkpointer,
        )

        app.state.lead_generation_graph = graph

        yield

        await discovery_client.aclose()
        await research_client.aclose()


app = FastAPI(
    title="Agent Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(
    lead_generation_router,
)


@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": (
            "agent-orchestrator"
        ),
    }