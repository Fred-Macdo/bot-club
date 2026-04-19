import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")

from dotenv import load_dotenv  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

# Load environment variables from .env file
# This looks for .env in the backend directory (parent of src)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.database import Database  # noqa: E402

from .routes import auth, user, user_config, strategy, backtest_routes, trading_routes  # noqa: E402
from .database.client import db_client  # noqa: E402
from .utils.redis_client import redis_client  # noqa: E402
from .utils.websocket_manager import websocket_manager  # noqa: E402
from .services.default_strategies import initialize_default_strategies  # noqa: E402

# Global database client
mongo_client: MongoClient | None = None
database: Database | None = None


def _ensure_indexes(db: Database):
    """Create MongoDB indexes for frequently queried collections."""
    from pymongo import ASCENDING

    db.user.create_index("email", unique=True, background=True)
    db.user.create_index("userName", unique=True, background=True)
    db.strategy.create_index("user_id", background=True)
    db.trading_sessions.create_index(
        [
            ("strategy_id", ASCENDING),
            ("user_id", ASCENDING),
            ("config.mode", ASCENDING),
        ],
        background=True,
    )
    db.trading_sessions.create_index("task_id", background=True)
    db.trading_sessions.create_index(
        [("user_id", ASCENDING), ("config.mode", ASCENDING)],
        background=True,
    )
    db.backtests.create_index("user_id", background=True)
    db.backtests.create_index("backtest_id", unique=True, background=True)
    db.backtest_executions.create_index("backtest_id", background=True)
    db.strategy_portfolios.create_index(
        [("strategy_id", ASCENDING), ("user_id", ASCENDING), ("mode", ASCENDING)],
        background=True,
    )
    db.user_config.create_index("user_id", unique=True, background=True)
    print("MongoDB indexes ensured")


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
    mongo_client = MongoClient(
        os.getenv("MONGO_URL", "mongodb://mongo:27017/"),
        maxPoolSize=50,
        minPoolSize=5,
        maxIdleTimeMS=45000,
        waitQueueTimeoutMS=30000,
        serverSelectionTimeoutMS=5000,
    )
    database = mongo_client[os.getenv("MONGO_DB_NAME", "bot_club_db")]

    # Store database in app state for dependency injection
    app.state.db = database

    # Also update db_client for dependencies.py to work
    db_client.database = database
    db_client.client = mongo_client
    db_client._connected = True

    # Ensure MongoDB indexes exist
    try:
        _ensure_indexes(database)
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")

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
    lifespan=lifespan,
)
# --- CORS Middleware Configuration ---
origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
allowed_headers = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
]

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
