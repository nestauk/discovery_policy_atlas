from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from app.core.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown events
    """
    # Startup
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    
    # Create necessary directories
    Path(settings.TEMP_FILES_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.EXPORT_FILES_DIR).mkdir(parents=True, exist_ok=True)
    
    # Validate settings
    try:
        settings.validate_llm_settings()
        logger.info("Settings validated successfully")
    except ValueError as e:
        logger.error(f"Settings validation failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

# Health check endpoint at root
@app.get("/")
async def root():
    return {
        "message": f"{settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """
    Comprehensive health check
    """
    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "settings": {
            "llm_provider": settings.LLM_PROVIDER,
            "llm_model": settings.LLM_MODEL,
            "openalex_configured": bool(settings.OPENALEX_EMAIL),
            "mediacloud_configured": bool(settings.MEDIACLOUD_API_KEY),
        }
    }
    
    # Check API keys
    if settings.LLM_PROVIDER == "openai":
        health_status["openai_configured"] = bool(settings.OPENAI_API_KEY)
    
    return health_status

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )