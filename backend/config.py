from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
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
    workspace_base: Path = Field(Path("./workspace"), alias="WORKSPACE_BASE")

    # Database (v2: PostgreSQL)
    database_url: str = Field(
        "postgresql://postgres:postgres@localhost:5432/gbads",
        alias="DATABASE_URL",
    )

    # GitHub OAuth (v2)
    github_client_id: str = Field("", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field("", alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str = Field(
        "http://localhost:8000/auth/github/callback", alias="GITHUB_REDIRECT_URI"
    )
    frontend_url: str = Field("http://localhost:5173", alias="FRONTEND_URL")

    # JWT (v2)
    jwt_secret_key: str = Field("change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_expire_hours: int = Field(72, alias="JWT_EXPIRE_HOURS")

    model_config = {
        "env_file": (".env", "../.env"),
        "populate_by_name": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
