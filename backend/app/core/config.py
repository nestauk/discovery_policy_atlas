from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Configuration
    PROJECT_NAME: str = "Policy Atlas API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"] 
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True
    
    # OpenAlex Configuration
    OPENALEX_EMAIL: Optional[str] = None
    
    # MediaCloud Configuration  
    MEDIACLOUD_API_KEY: Optional[str] = None
    MEDIACLOUD_BASE_URL: str = "https://api.mediacloud.org/api/v4"
    
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
    DEFAULT_MAX_RESULTS: int = 10
    DEFAULT_MIN_CITATIONS: int = 5
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )
    
    @property
    def llm_config(self) -> dict:
        """Get LLM configuration based on provider"""
        if self.LLM_PROVIDER == "openai":
            return {
                "model": self.LLM_MODEL,
                "temperature": self.LLM_TEMPERATURE,
                "max_tokens": self.LLM_MAX_TOKENS,
                "api_key": self.OPENAI_API_KEY
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