from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine

app = FastAPI(
    title="Research service",
    version="0.1.0"
)

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