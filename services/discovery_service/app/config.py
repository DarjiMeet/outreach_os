from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    tavily_api_key: str
    groq_key: str
    research_service_url: str
    discovery_max_rounds: int = Field(default=3, ge=1, le=10)
    discovery_timeout_seconds: float = Field(default=180.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
