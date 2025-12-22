"""
Backend Service Entry Point

This module initializes and runs the backend service with:
- MongoDB connection
- Backtest service
- Trading endpoints
- WebSocket support for live logs
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
import uvicorn

from config import (
    MONGO_HOST, MONGO_PORT, MONGO_URL, MONGO_DB, LOG_LEVEL, SERVICE_PORT
)
from services.backtest.backtest_service import BacktestService
from services.utils.websocket_manager import websocket_manager
from api.routers import health, backtest, trading, websocket
from api.celery_trading_manager import celery_trading_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackendService:
    """
    Main application state container.
    Holds database connections and service references.
    """
    
    def __init__(self):
        self.db_client = None
        self.db = None
        self.backtest_service = None
        self.trading_service = None

    async def startup(self):
        """Initialize database and services."""
        # Initialize MongoDB connection
        logger.info(f"Connecting to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        self.db_client = AsyncMongoClient(MONGO_URL)
        self.db = self.db_client[MONGO_DB]
        logger.info(f"Connected to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        
        # Initialize backtest service
        logger.info("Initializing backtest service")
        self.backtest_service = BacktestService(self.db)
        await self.backtest_service.initialize()
        
        # Initialize WebSocket manager (connects to Redis for pub/sub)
        logger.info("Initializing WebSocket manager")
        try:
            # Assuming websocket_manager has an initialize method, if not, we can skip or check
            if hasattr(websocket_manager, 'initialize'):
                await websocket_manager.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize WebSocket manager: {e}")
            logger.warning("WebSocket manager will initialize lazily on first connection")

        logger.info("Backend service started successfully")

    async def cleanup(self):
        """Cleanup resources on shutdown."""
        logger.info("Shutting down services...")
        
        # Stop all running traders
        await celery_trading_manager.stop_all()
        
        # Shutdown WebSocket manager
        if hasattr(websocket_manager, 'shutdown'):
            await websocket_manager.shutdown()
        
        # Shutdown backtest service
        if self.backtest_service:
            await self.backtest_service.shutdown()
        
        # Close database connection
        if self.db_client:
            self.db_client.close()
            logger.info("Database connection closed")

service = BackendService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await service.startup()
    app.state.db_client = service.db_client
    app.state.db = service.db
    app.state.backtest_service = service.backtest_service
    # app.state.trading_service = service.trading_service # Not initialized in startup?
    
    yield
    
    await service.cleanup()

app = FastAPI(lifespan=lifespan)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"},
    )

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(backtest.router)
app.include_router(trading.router)
app.include_router(websocket.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(SERVICE_PORT), reload=True)
