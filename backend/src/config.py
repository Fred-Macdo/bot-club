import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MongoDB settings
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB = os.getenv("MONGO_DB", "bot_club_db")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "bot_club_db")  # Legacy compatibility

# For development/docker without auth
MONGO_URL = os.getenv("MONGO_URL", f"mongodb://{MONGO_HOST}:{MONGO_PORT}")

# Legacy auth settings (if needed for production)
MONGO_USER = os.getenv("MONGO_USER", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")

# Redis settings for message queue and Celery
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}")

# Service settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BACKTEST_WORKERS = int(os.getenv("BACKTEST_WORKERS", 2))
SERVICE_PORT = int(os.getenv("SERVICE_PORT", 8000))

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")