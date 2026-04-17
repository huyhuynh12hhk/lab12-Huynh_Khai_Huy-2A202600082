"""
Configuration — 12-Factor App: all config from environment variables.
Uses pydantic-settings so each field is auto-loaded from the environment.
A .env file is supported automatically during local development.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
import logging


class Settings(BaseSettings):
    """All runtime configuration lives here.  Never hardcode values in app code."""

    # ── Server ──────────────────────────────────────────────────────────
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")
    environment: str = Field("development", alias="ENVIRONMENT")
    debug: bool = Field(False, alias="DEBUG")

    # ── App identity ─────────────────────────────────────────────────────
    app_name: str = Field("Production AI Agent", alias="APP_NAME")
    app_version: str = Field("1.0.0", alias="APP_VERSION")

    # ── Security ─────────────────────────────────────────────────────────
    # API key that clients must send in the X-API-Key header.
    # CHANGE this in production — never leave the default value!
    agent_api_key: str = Field("dev-key-change-me", alias="AGENT_API_KEY")

    # ── Rate limiting ────────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(10, alias="RATE_LIMIT_PER_MINUTE")

    # ── Cost / budget guard ──────────────────────────────────────────────
    # Maximum USD spend per user per calendar month before blocking.
    monthly_budget_usd: float = Field(10.0, alias="MONTHLY_BUDGET_USD")

    # ── Storage ──────────────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    class Config:
        # Load from a .env file when present (handy for local development).
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow both the aliased (UPPER_CASE) and the field name.
        populate_by_name = True

    def validate_production(self) -> "Settings":
        """Enforce stricter checks when ENVIRONMENT=production."""
        logger = logging.getLogger(__name__)
        if self.environment == "production":
            if self.agent_api_key == "dev-key-change-me":
                raise ValueError("AGENT_API_KEY must be set to a real secret in production!")
        if not self.environment == "production":
            logger.warning("Running in '%s' mode — mock LLM active", self.environment)
        return self


settings = Settings().validate_production()
