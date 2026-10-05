from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.dependencies import get_lead_generation_graph
from app.graphs.lead_generation_graph import LeadGenerationGraph
from app.schemas.lead_generation import LeadGenerationRequest


router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
)


@router.post("/lead-generation")
async def generate_leads(
    request: LeadGenerationRequest,
    graph: LeadGenerationGraph = Depends(
        get_lead_generation_graph
    ),
):
    thread_id = str(uuid4())

    initial_state = request.model_dump()

    result = await graph.run(
        initial_state=initial_state,
        thread_id=thread_id,
    )

    interrupts = result.get(
        "__interrupt__",
        (),
    )

    if interrupts:
        return {
            "thread_id": thread_id,
            "status": "waiting_for_research",
            "interrupt": interrupts[0].value,
            "discovery_summary": result.get("discovery_summary", {}),
        }

    return {
        "thread_id": thread_id,
        "status": "completed",
        "state": result,
    }


@router.post(
    "/lead-generation/{thread_id}/resume"
)
async def resume_lead_generation(
    thread_id: str,
    graph: LeadGenerationGraph = Depends(
        get_lead_generation_graph
    ),
):
    result = await graph.resume(
        thread_id=thread_id
    )

    interrupts = result.get(
        "__interrupt__",
        (),
    )

    if interrupts:
        return {
            "thread_id": thread_id,
            "status": "waiting_for_research",
            "interrupt": interrupts[0].value,
            "discovery_summary": result.get("discovery_summary", {}),
        }

    return {
        "thread_id": thread_id,
        "status": "completed",
        "state": result,
    }


@router.get(
    "/lead-generation/{thread_id}"
)
async def get_lead_generation_state(
    thread_id: str,
    graph: LeadGenerationGraph = Depends(
        get_lead_generation_graph
    ),
):
    state = await graph.get_state(
        thread_id=thread_id
    )

    return {
        "thread_id": thread_id,
        "state": state,
    }
