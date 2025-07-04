from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List, Union
from functools import lru_cache
from pydantic import field_validator
import json
import logging

# Set up logger
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Configuration
    PROJECT_NAME: str = "Policy Atlas API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # CORS - Use Union to prevent automatic JSON parsing
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = ["http://localhost:3000"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from string or list input"""
        # Track what happened for logging
        default_origins = ["http://localhost:3000"]

        if v is None:
            logger.warning(
                "BACKEND_CORS_ORIGINS not set, using default: %s", default_origins
            )
            return default_origins

        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                logger.warning(
                    "BACKEND_CORS_ORIGINS is empty, using default: %s", default_origins
                )
                return default_origins

            # Try JSON parsing first
            if v.strip().startswith("["):
                try:
                    parsed = json.loads(v)
                    logger.info("BACKEND_CORS_ORIGINS parsed from JSON: %s", parsed)
                    return parsed
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Failed to parse BACKEND_CORS_ORIGINS as JSON: %s", e
                    )

            # Fall back to comma-separated
            origins = [origin.strip() for origin in v.split(",") if origin.strip()]
            if origins:
                logger.info(
                    "BACKEND_CORS_ORIGINS parsed from comma-separated: %s", origins
                )
                return origins
            else:
                logger.warning(
                    "BACKEND_CORS_ORIGINS parsing failed, using default: %s",
                    default_origins,
                )
                return default_origins

        if isinstance(v, list):
            logger.info("BACKEND_CORS_ORIGINS using list value: %s", v)
            return v

        # Unexpected type
        logger.error(
            "BACKEND_CORS_ORIGINS has unexpected type %s, using default: %s",
            type(v),
            default_origins,
        )
        return default_origins

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # OpenAlex Configuration
    OPENALEX_EMAIL: Optional[str] = None

    # MediaCloud Configuration
    MEDIACLOUD_API_KEY: Optional[str] = None
    MEDIACLOUD_BASE_URL: str = "https://api.mediacloud.org/api/v4"

    # Overton Configuration
    OVERTON_API_KEY: Optional[str] = None

    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = None

    # LLM Model Settings
    LLM_PROVIDER: str = "openai"  # "openai" or "anthropic"
    LLM_MODEL: str = "gpt-4o-mini"  # or "claude-3-haiku-20240307"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4000

    # Batch Processing Settings
    BATCH_SIZE_SCREENING: int = 5
    BATCH_SIZE_EXTRACTION: int = 3
    BATCH_SLEEP_TIME: float = 0.5  # Seconds between API calls

    # File Storage
    TEMP_FILES_DIR: str = "./temp"
    EXPORT_FILES_DIR: str = "./exports"

    # Rate Limiting
    OPENALEX_RATE_LIMIT: int = 10  # requests per second
    MEDIACLOUD_RATE_LIMIT: int = 5  # requests per second

    # Search Defaults
    DEFAULT_MAX_RESULTS: int = 50
    MAX_SEARCH_RESULTS: int = 1000  # Maximum allowed search results
    DEFAULT_MIN_CITATIONS: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra environment variables
    )

    @property
    def llm_config(self) -> dict:
        """Get LLM configuration based on provider"""
        if self.LLM_PROVIDER == "openai":
            return {
                "model": self.LLM_MODEL,
                "temperature": self.LLM_TEMPERATURE,
                "max_tokens": self.LLM_MAX_TOKENS,
                "api_key": self.OPENAI_API_KEY,
            }
        else:
            raise ValueError(f"Unknown LLM provider: {self.LLM_PROVIDER}")

    def validate_llm_settings(self):
        """Validate LLM settings on startup"""
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'")

    def validate_api_keys(self):
        """Validate required API keys based on features used"""
        # This can be called selectively based on which features are used
        pass


@lru_cache()
def get_settings() -> Settings:
    """
    Create cached settings instance
    Use this function to get settings throughout the app
    """
    settings = Settings()
    settings.validate_llm_settings()
    return settings


# Create a single instance for easy import
settings = get_settings()
