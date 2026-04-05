
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")

from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# This looks for .env in the backend directory (parent of src)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pymongo import MongoClient
from pymongo.database import Database

from .routes import auth, user, user_config, strategy, backtest_routes, trading_routes
from .database.client import db_client
from .utils.redis_client import redis_client
from .utils.websocket_manager import websocket_manager
from .services.default_strategies import initialize_default_strategies

# Global database client
mongo_client: MongoClient | None = None
database: Database | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    This ensures proper initialization and cleanup of resources.
    """
    # Startup
    global mongo_client, database
    
    print("Starting up application...")
    
    # Initialize MongoDB connection
    mongo_client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongo:27017/"))
    database = mongo_client[os.getenv("MONGO_DB_NAME", "bot_club_db")]
    
    # Store database in app state for dependency injection
    app.state.db = database
    
    # Also update db_client for dependencies.py to work
    db_client.database = database
    db_client.client = mongo_client
    db_client._connected = True
    
    # Initialize Redis connection
    try:
        await redis_client.connect()
        app.state.redis = redis_client
        print("Redis initialized successfully")
    except Exception as e:
        print(f"Error initializing Redis: {e}")
        # Don't fail startup if Redis can't be initialized
    
    # Initialize default strategies (only creates if they don't exist)
    try:
        await initialize_default_strategies(database)
        print("Default strategies initialized successfully")
    except Exception as e:
        print(f"Error initializing default strategies: {e}")
        # Don't fail startup if default strategies can't be initialized
    
    yield  # Application runs
    
    # Shutdown
    print("Shutting down application...")
    
    # Disconnect from Redis
    try:
        await redis_client.disconnect()
    except Exception as e:
        print(f"Error disconnecting Redis: {e}")
    
    # Disconnect from MongoDB
    if mongo_client:
        mongo_client.close()


# Create FastAPI app with lifespan events
app = FastAPI(
    title="Bot Club API",
    description="Algorithmic Trading Platform API",
    version="1.0.0",
    lifespan=lifespan
)
# --- CORS Middleware Configuration ---
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
allowed_headers = ["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
    expose_headers=["Content-Length", "X-Request-Id"],
)
# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(user.router, prefix="/api/users", tags=["users"])
app.include_router(user_config.router, prefix="/api/user-config", tags=["user-config"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategies"])
app.include_router(backtest_routes.router, prefix="/api/backtest", tags=["backtests"])
app.include_router(trading_routes.router, prefix="/api/trading", tags=["trading"])

@app.websocket("/ws/task/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    last_id = websocket.query_params.get("last_id", "0")
    await websocket_manager.connect(websocket, task_id, last_id=last_id)

@app.get("/")
async def root():
    return {"message": "Trading Bot API", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint for container monitoring"""
    health = {"status": "healthy"}
    
    # Check MongoDB
    try:
        await database.command("ping")
        health["database"] = "connected"
    except Exception as e:
        health["status"] = "unhealthy"
        health["database"] = f"disconnected: {str(e)}"
    
    # Check Redis
    try:
        if redis_client.redis:
            await redis_client.redis.ping()
            health["redis"] = "connected"
        else:
            health["redis"] = "not initialized"
    except Exception as e:
        health["status"] = "unhealthy"
        health["redis"] = f"disconnected: {str(e)}"
    
    return health