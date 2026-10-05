from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine
from app.api.routes.research import router as research_router

app = FastAPI(
    title="Research service",
    version="0.1.0"
)

app.include_router(research_router)

@app.get("/health")
async def health():
    return {
        "status":"ok",
        "service":"research-service"
    }

@app.get("/health/db")
async def database_health():
    async with engine.connect() as connection:
        result  = await connection.execute(text("SELECT 1"))
    return {
        "status":   "ok",
        "database": result.scalar() == 1
    }