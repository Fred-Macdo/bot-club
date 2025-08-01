
from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# This looks for .env in the backend directory (parent of src)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient

from .routes import auth, user, user_config, strategy, backtest_routes, trading_routes
from .database.client import db_client
from .utils.redis_client import redis_client
from .services.default_strategies import initialize_default_strategies

# Global database client
motor_client = None
database = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    This ensures proper initialization and cleanup of resources.
    """
    # Startup
    global motor_client, database
    
    print("Starting up application...")
    
    # Initialize MongoDB connection
    motor_client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://mongo:27017/"))
    database = motor_client[os.getenv("MONGO_DB_NAME", "bot_club_db")]
    
    # Store database in app state for dependency injection
    app.state.db = database
    
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
    if motor_client:
        motor_client.close()


# Create FastAPI app with lifespan events
app = FastAPI(
    title="Bot Club API",
    description="Algorithmic Trading Platform API",
    version="1.0.0",
    lifespan=lifespan
)
# --- CORS Middleware Configuration ---
origins = [
    "http://localhost:3000",
    "http://localhost:3001",  # Add additional frontend ports if needed
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

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

@app.get("/")
async def root():
    return {"message": "Trading Bot API", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint for container monitoring"""
    try:
        # Test database connection
        await database.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}