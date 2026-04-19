from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# This looks for .env in the backend directory (parent of src)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Alternative: Load from current directory and parent directories
# load_dotenv()

from pymongo import MongoClient
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo.database import Database
from bson import ObjectId
from jose import JWTError, jwt
from typing import Optional, AsyncGenerator
import logging

# Ensure correct relative imports based on your project structure
from .models.user import UserInDB
from .database.client import db_client
from .crud.user import get_user_by_mongodb_id

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection globals - initialized in startup
client: Optional[MongoClient] = None

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "your-secret-key-change-this-in-production":
    raise ValueError("JWT_SECRET_KEY must be set in .env file")
ALGORITHM = "HS256"

# Security — Bearer header is optional so we can fall back to cookie
security = HTTPBearer(auto_error=False)


def _extract_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str:
    """Extract JWT from Bearer header or httpOnly cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    token = request.cookies.get("access_token")
    if token:
        return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_mongo_url():
    """Get MongoDB connection URL based on environment"""
    local = os.getenv("LOCAL_DB", "false").lower() == "true"
    
    if local:
        return os.getenv("MONGO_URL", "mongodb://mongo:27017/")  # Use docker service name
    else:
        # For MongoDB Atlas
        username = os.getenv("MONGO_USERNAME", "fred-bot-club")
        password = os.getenv("MONGO_PASSWORD")  # This should be set in environment
        cluster = os.getenv("MONGO_CLUSTER", "bot-club-cluster.b9yda9w.mongodb.net")
        
        if not password:
            raise ValueError("MONGO_PASSWORD environment variable is required for Atlas connection")
        
        return f"mongodb+srv://{username}:{password}@{cluster}/bot_club_db?retryWrites=true&w=majority"

async def connect_to_mongo():
    """Initialize MongoDB connection - called during startup"""
    global client
    
    try:
        mongo_url = get_mongo_url()
        client = MongoClient(mongo_url)
        
        # Test the connection
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Close MongoDB connection - called during shutdown"""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")

async def get_db() -> AsyncGenerator[Database, None]:
    """
    FastAPI dependency that provides a database session.
    It connects on startup and disconnects on shutdown via the lifespan manager.
    """
    # This check ensures that the app's state has been initialized
    # before any dependency tries to access the database.
    if not hasattr(db_client, 'database') or db_client.database is None:
        raise HTTPException(
            status_code=500,
            detail="Database client is not initialized. Check application startup.",
        )
    yield db_client.database


async def get_current_user_from_token(
    request: Request,
    token: HTTPAuthorizationCredentials = Depends(security), 
    db: Database = Depends(get_db)
) -> UserInDB:
    """Get current user from JWT token (Bearer header or httpOnly cookie)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    raw_token = _extract_token(request, token)
    
    try:
        # Decode JWT token
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    user = await get_user_by_mongodb_id(db, user_id)
    if user is None:
        raise credentials_exception
    
    return user