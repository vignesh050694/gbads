from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    model_id: str = "claude-sonnet-4-6"
    max_tokens_per_call: int = 8192

    # Loop
    max_iterations: int = Field(10, alias="GBADS_MAX_ITERATIONS")
    hard_ceiling: int = Field(50, alias="GBADS_HARD_CEILING")
    target_score: float = Field(1.0, alias="GBADS_TARGET_SCORE")

    # Sandbox
    sandbox_timeout: int = Field(30, alias="GBADS_SANDBOX_TIMEOUT")

    # Paths
    output_dir: Path = Field(Path("./output"), alias="GBADS_OUTPUT_DIR")

    # Database
    database_url: str = Field(
        "postgresql://localhost/gbads", alias="DATABASE_URL"
    )

    model_config = {"env_file": ".env", "populate_by_name": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
