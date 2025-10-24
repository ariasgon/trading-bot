"""
Main FastAPI application for the trading bot.
"""
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime

from app.core.config import settings
from app.core.database import init_db, check_db_connection
from app.core.cache import redis_cache
from app.api import trading, monitoring, strategy, bot_control, test_ov, backtesting, trade_history, settings as settings_api

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Trading Bot application...")
    
    try:
        # Initialize database - TEMPORARILY DISABLED
        # init_db()

        # Check connections - TEMPORARILY DISABLED
        # if not check_db_connection():
        #     raise Exception("Database connection failed")

        # if not redis_cache.health_check():
        #     raise Exception("Redis connection failed")

        logger.info("All services initialized successfully (DB/Redis checks disabled)")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Trading Bot application...")


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Automated trading bot based on Oliver Velez methodology",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database
        db_healthy = check_db_connection()
        
        # Check Redis
        redis_healthy = redis_cache.health_check()
        
        status = "healthy" if (db_healthy and redis_healthy) else "unhealthy"
        
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "version": settings.app_version,
            "services": {
                "database": "up" if db_healthy else "down",
                "redis": "up" if redis_healthy else "down"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "status": "running",
        "docs_url": "/docs"
    }


# Include API routers
app.include_router(
    trading.router,
    prefix="/api/v1/trading",
    tags=["trading"]
)

app.include_router(
    monitoring.router,
    prefix="/api/v1/monitoring",
    tags=["monitoring"]
)

app.include_router(
    strategy.router,
    prefix="/api/v1/strategy",
    tags=["strategy"]
)

app.include_router(
    bot_control.router,
    prefix="/api/v1/bot",
    tags=["bot_control"]
)

app.include_router(
    test_ov.router,
    prefix="/api/v1/test-ov",
    tags=["test_ov"]
)

app.include_router(
    backtesting.router,
    tags=["backtesting"]
)

app.include_router(
    trade_history.router,
    prefix="/api/v1/history",
    tags=["trade_history"]
)

app.include_router(
    settings_api.router,
    prefix="/api/v1/settings",
    tags=["settings"]
)

# Crypto API router - DISABLED for stock trading only
# try:
#     from app.api import crypto_api
#     app.include_router(
#         crypto_api.router,
#         prefix="/api/v1/crypto",
#         tags=["crypto"]
#     )
#     logger.info("Crypto API routes loaded successfully")
# except ImportError as e:
#     logger.warning(f"Crypto API not available: {e}")
# except Exception as e:
#     logger.error(f"Failed to load crypto API: {e}")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Add dashboard route for new backtesting dashboard
from fastapi.responses import FileResponse

@app.get("/dashboard")
async def get_dashboard():
    """Serve the enhanced dashboard with backtesting."""
    return FileResponse("app/static/dashboard_with_backtesting.html")

@app.get("/dashboard/legacy")
async def get_legacy_dashboard():
    """Serve the original dashboard."""
    return FileResponse("app/static/dashboard.html")

@app.get("/dashboard/history")
async def get_history_dashboard():
    """Serve the trade history and P/L analytics dashboard."""
    return FileResponse("app/static/trade_history.html")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )