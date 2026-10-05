from fastapi import Request

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


def get_lead_generation_graph(request: Request)->LeadGenerationGraph:

    return (
        request.app.state.lead_generation_graph
    )