from fastapi import FastAPI

from app.api.routes.discovery import (
    router as discovery_router,
)


app = FastAPI(
    title="Discovery Service",
    version="0.1.0",
)

app.include_router(discovery_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "discovery-service",
    }