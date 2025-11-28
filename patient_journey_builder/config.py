"""
Configuration module for Patient Journey Builder.

Uses Pydantic Settings for environment variable support and validation.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, Literal
from pathlib import Path


class Settings(BaseSettings):
    """
    Application configuration with environment variable support.

    All settings can be overridden via environment variables or .env file.
    """

    # API Keys
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    brave_api_key: Optional[str] = Field(
        default=None,
        description="Brave Search API key (required for standard mode, optional for intelligent mode)"
    )

    # Research mode
    intelligent_mode: bool = Field(
        default=True,
        description="Use Claude intelligent search instead of Brave API (recommended for quality)"
    )

    # Model settings
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for synthesis"
    )
    max_output_tokens: int = Field(
        default=8000,
        description="Maximum tokens for Claude output"
    )

    # Search settings
    searches_per_domain: int = Field(
        default=17,
        description="Number of search queries per domain"
    )
    max_search_results: int = Field(
        default=10,
        description="Maximum results per search query"
    )
    top_results_to_fetch: int = Field(
        default=3,
        description="Number of top results to fetch full content for"
    )

    # Rate limiting (base values - adaptive limiter adjusts these)
    search_delay_seconds: float = Field(
        default=1.0,
        ge=0.5,
        description="Base delay between search requests"
    )
    api_delay_seconds: float = Field(
        default=2.0,
        ge=1.0,
        description="Base delay between Claude API calls"
    )

    # Retry settings
    max_retries: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed requests"
    )
    retry_min_wait: float = Field(
        default=2.0,
        description="Minimum wait between retries (seconds)"
    )
    retry_max_wait: float = Field(
        default=60.0,
        description="Maximum wait between retries (seconds)"
    )

    # Validation settings
    strict_mode: bool = Field(
        default=False,
        description="If True, fail on validation errors instead of continuing"
    )
    min_rows_per_table: int = Field(
        default=2,
        description="Minimum rows required per table for validation"
    )
    max_synthesis_retries: int = Field(
        default=2,
        description="Retries for Claude synthesis if output has gaps"
    )

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level"
    )
    log_file: Optional[str] = Field(
        default=None,
        description="Optional log file path"
    )
    json_logs: bool = Field(
        default=False,
        description="Output logs as JSON (for production)"
    )

    # Paths
    cache_dir: str = Field(default="data/cache")
    session_dir: str = Field(default="data/sessions")
    output_dir: str = Field(default="data/outputs")
    cost_dir: str = Field(default="data/costs")
    localization_dir: Optional[str] = Field(
        default=None,
        description="Directory for custom country configs"
    )

    # Feature flags
    enable_cost_tracking: bool = Field(
        default=True,
        description="Track and report API costs"
    )
    enable_pdf_extraction: bool = Field(
        default=True,
        description="Attempt to extract content from PDF links"
    )

    model_config = {
        "env_file": [
            ".env",
            Path(__file__).parent / ".env",
        ],
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @field_validator("cache_dir", "session_dir", "output_dir", "cost_dir", mode="before")
    @classmethod
    def ensure_directories_exist(cls, v: str) -> str:
        """Create directories if they don't exist."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Validate Anthropic API key is not empty or placeholder values."""
        if not v or v.startswith("your-") or v == "xxx" or v == "sk-ant-your-key-here":
            raise ValueError("Anthropic API key must be set to a valid value")
        return v

    @field_validator("brave_api_key", mode="before")
    @classmethod
    def validate_brave_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate Brave API key if provided."""
        if v is None or v == "":
            return None
        if v.startswith("your-") or v == "xxx":
            raise ValueError("Brave API key must be set to a valid value or left empty for intelligent mode")
        return v


def get_settings() -> Settings:
    """
    Get application settings.

    Returns cached settings instance for efficiency.
    """
    return Settings()
