
from dotenv import load_dotenv
import os
from pathlib import Path
import logging

# Load environment variables from .env file
# This looks for .env in the backend directory (parent of src)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database as SyncDatabase

from .routes import auth, user, user_config, strategy, backtest_routes, trading_routes
from .api.routers import health, websocket
from .database.client import db_client
from .utils.redis_client import redis_client
from .services.default_strategies import initialize_default_strategies
from .services.backtest.backtest_service import BacktestService
from .api.celery_trading_manager import celery_trading_manager
from .services.utils_extended.websocket_manager import websocket_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format='%(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global database clients (async Motor and sync PyMongo for backward compatibility)
async_mongo_client: AsyncIOMotorClient | None = None
async_database = None
sync_mongo_client = None
sync_database: SyncDatabase | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    This ensures proper initialization and cleanup of resources.
    """
    # Startup
    global async_mongo_client, async_database, sync_mongo_client, sync_database
    
    logger.info("Starting up application...")
    
    mongo_url = os.getenv("MONGO_URL", "mongodb://mongo:27017/")
    mongo_db_name = os.getenv("MONGO_DB_NAME", "bot_club_db")
    
    # Initialize async MongoDB connection (Motor)
    async_mongo_client = AsyncIOMotorClient(mongo_url)
    async_database = async_mongo_client[mongo_db_name]
    
    # Initialize sync MongoDB for backward compatibility (will phase out)
    from pymongo import MongoClient
    sync_mongo_client = MongoClient(mongo_url)
    sync_database = sync_mongo_client[mongo_db_name]
    
    # Store databases in app state for dependency injection
    app.state.db = sync_database  # Legacy sync access
    app.state.async_db = async_database  # New async access
    app.state.db_client = async_mongo_client
    
    # Update db_client for legacy dependencies.py to work
    db_client.database = sync_database
    db_client.client = sync_mongo_client
    db_client._connected = True
    
    # Initialize Redis connection
    try:
        await redis_client.connect()
        app.state.redis = redis_client
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Redis: {e}")
    
    # Initialize BacktestService
    logger.info("Initializing backtest service")
    backtest_service = BacktestService(async_database)
    await backtest_service.initialize()
    app.state.backtest_service = backtest_service
    
    # Initialize WebSocket manager
    logger.info("Initializing WebSocket manager")
    try:
        if hasattr(websocket_manager, 'initialize'):
            await websocket_manager.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize WebSocket manager: {e}")
        logger.warning("WebSocket manager will initialize lazily on first connection")
    
    # Initialize default strategies (only creates if they don't exist)
    try:
        await initialize_default_strategies(sync_database)
        logger.info("Default strategies initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing default strategies: {e}")
    
    logger.info("Backend service started successfully")
    
    yield  # Application runs
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Stop all running traders
    await celery_trading_manager.stop_all()
    
    # Shutdown WebSocket manager
    if hasattr(websocket_manager, 'shutdown'):
        await websocket_manager.shutdown()
    
    # Shutdown backtest service
    if backtest_service:
        await backtest_service.shutdown()
    
    # Disconnect from Redis
    try:
        await redis_client.disconnect()
    except Exception as e:
        logger.error(f"Error disconnecting Redis: {e}")
    
    # Disconnect from MongoDB
    if async_mongo_client:
        async_mongo_client.close()
    if sync_mongo_client:
        sync_mongo_client.close()


# Create FastAPI app with lifespan events
app = FastAPI(
    title="Bot Club API",
    description="Algorithmic Trading Platform API",
    version="1.0.0",
    lifespan=lifespan
)
# --- CORS Middleware Configuration ---
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(user.router, prefix="/api/users", tags=["users"])
app.include_router(user_config.router, prefix="/api/user-config", tags=["user-config"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategies"])
app.include_router(backtest_routes.router, prefix="/api/backtest", tags=["backtests"])
app.include_router(trading_routes.router, prefix="/api/trading", tags=["trading"])

# Include new routers from backend_services
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(websocket.router, prefix="/api", tags=["websocket"])

@app.get("/")
async def root():
    return {"message": "Trading Bot API", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint for container monitoring"""
    try:
        # Test async database connection
        await async_database.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}