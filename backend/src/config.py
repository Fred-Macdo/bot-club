import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "bot_club_db")
BACKEND_SERVICES_URL = os.getenv("BACKEND_SERVICES_URL", "http://backend_services:8001")

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")