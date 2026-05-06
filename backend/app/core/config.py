import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory (3 levels up from this config file)
config_dir = Path(__file__).parent.parent.parent

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
    OPENALEX_API_KEY: Optional[str] = None

    # MediaCloud Configuration
    MEDIACLOUD_API_KEY: Optional[str] = None
    MEDIACLOUD_BASE_URL: str = "https://api.mediacloud.org/api/v4"

    # Overton Configuration
    OVERTON_API_KEY: Optional[str] = None

    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = None

    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None

    # Development/Testing
    MOCK_OPENAI: bool = False
    DEBUG_ANALYSIS_FILES: bool = False  # Keep local analysis files for debugging

    # LLM Model Settings
    LLM_PROVIDER: str = "OpenAI"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4000
    CHATBOT_MODEL: str = "gpt-4o-mini"
    CHATBOT_REASONING_EFFORT: str = "minimal"
    # Model for structured C/M extraction and the critic pass during deep dive
    CHATBOT_EXTRACTION_MODEL: str = "gpt-4.1-mini"

    # Boolean Query Generation Settings
    BOOLEAN_QUERY_GENERATION_MODE: str = "multi"  # "single" or "multi"
    BOOLEAN_QUERY_TEMPERATURE: float = 1.0  # Temperature for query generation
    BOOLEAN_QUERY_N_RUNS: int = 5  # Number of queries to generate in multi mode
    BOOLEAN_QUERY_MODEL: str = "gpt-4.1"  # Model for query generation

    # Search Wizard Settings
    SEARCH_WIZARD_MODEL: str = (
        "gpt-4.1-mini"
    )  # Model for search wizard (population/outcome options, additional questions)

    # Screening/Relevance Settings
    SCREENING_MODEL: str = "gpt-4.1-mini"  # Model for screening and relevance checking
    EVIDENCE_CATEGORY_MODEL: str = (
        "gpt-5.2"  # Model for evidence categorisation (needs higher accuracy)
    )
    OPENALEX_ENABLE_RCT_SYSREV_FANOUT: bool = (
        True  # Fan out RCT/systematic review variants
    )

    # Batch Processing Settings
    BATCH_SIZE_SCREENING: int = 5
    BATCH_SIZE_EXTRACTION: int = 5  #
    BATCH_SLEEP_TIME: float = 0.5  # Seconds between API calls

    # Document Processing Limits
    MAX_DOCUMENT_CHARS: int = 75000  # Max chars for extraction (~18-20k tokens)
    MAX_DOCUMENT_TOKENS: int = 15000  # Token limit for LLM processing
    # Note: Workflow makes 5-7 LLM calls per document, so smaller limits = faster processing

    # PDF/File Limits (used during parsing)
    MAX_PDF_SIZE_MB: float = 50.0  # Maximum PDF file size
    MAX_PDF_PAGES: int = 50  # Maximum PDF pages
    MAX_TEXT_LENGTH_CHARS: int = (
        100000  # Max chars during parsing (before extraction truncation)
    )

    # Timeout Settings (seconds)
    DOWNLOAD_TIMEOUT: float = 30.0
    PDF_PARSE_TIMEOUT: float = 30.0
    HTML_PARSE_TIMEOUT: float = 10.0
    LLM_REQUEST_TIMEOUT: float = 120.0

    # Concurrency Settings (used by acquisition/extraction services)
    ACQUISITION_CONCURRENCY: int = 5

    # File Storage
    TEMP_FILES_DIR: str = str(config_dir / "temp")
    EXPORT_FILES_DIR: str = str(config_dir / "temp")

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
        if self.LLM_PROVIDER == "OpenAI":
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
        if self.LLM_PROVIDER == "OpenAI" and not self.OPENAI_API_KEY:
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
