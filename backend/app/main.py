from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from app.core.config import settings
from app.api.routes import router
from app.api.projects import router as projects_router
from app.api.test_extraction import router as test_extraction_router
from app.api.public import router as public_router
from app.services.download import download_service

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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

    # Clean up expired downloads on startup (useful when app wakes up from sleep)
    try:
        cleaned = download_service.force_cleanup()
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired download entries on startup")
        else:
            logger.info("No expired downloads to clean up on startup")
    except Exception as e:
        logger.error(f"Error cleaning up downloads on startup: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    # redirect_slashes=False,  # Disable automatic slash redirects
)

## Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)
app.include_router(projects_router)
app.include_router(test_extraction_router)
app.include_router(public_router)


# Health check endpoint at root
@app.get("/")
async def root():
    return {
        "message": f"{settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "status": "running",
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
        },
    }

    # Check API keys
    if settings.LLM_PROVIDER == "OpenAI":
        health_status["openai_configured"] = bool(settings.OPENAI_API_KEY)

    return health_status


@app.get("/debug/routes")
async def debug_routes():
    routes_list = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            routes_list.append(
                {
                    "path": route.path,
                    "methods": list(route.methods) if route.methods else [],
                    "name": route.name,
                }
            )
    return {"routes": routes_list}
