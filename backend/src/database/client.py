from pymongo.mongo_client import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from .env file in backend directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class DatabaseClient:
    def __init__(self):
        self.client: MongoClient | None = None
        self.database: Database | None = None
        self._connected = False

    def connect(self) -> Database:
        """Connect to MongoDB using PyMongo (sync)"""
        # Return existing database if already connected
        if self._connected and self.database is not None:
            return self.database

        try:
            # Check if we should use local MongoDB
            use_local = os.getenv("LOCAL_DB", "false").lower() == "true"

            if use_local:
                # Check if we're running in Docker (use service name) or local development
                mongo_url = os.getenv(
                    "MONGO_URL", "mongodb://localhost:27017/bot_club_db"
                )
                print(f"Connecting to local MongoDB: {mongo_url}")
                self.client = MongoClient(
                    mongo_url,
                    maxPoolSize=50,
                    minPoolSize=5,
                    maxIdleTimeMS=45000,
                    waitQueueTimeoutMS=30000,
                    serverSelectionTimeoutMS=5000,
                )
            else:
                # Use MongoDB Atlas
                connection_string = os.getenv("MONGO_CONNECTION_STRING")
                if not connection_string:
                    # Build connection string from components
                    username = os.getenv("MONGO_USERNAME")
                    password = os.getenv("MONGO_PASSWORD")
                    cluster = os.getenv("MONGO_CLUSTER")
                    connection_string = (
                        f"mongodb+srv://{username}:{password}@{cluster}/"
                    )

                print("Connecting to MongoDB Atlas")
                self.client = MongoClient(
                    connection_string,
                    maxPoolSize=50,
                    minPoolSize=5,
                    maxIdleTimeMS=45000,
                    waitQueueTimeoutMS=30000,
                    serverSelectionTimeoutMS=5000,
                )

            # Get database name
            db_name = os.getenv("MONGO_DB_NAME", "bot_club_db")
            self.database = self.client[db_name]

            # Test the connection
            self.client.admin.command("ping")
            print(f"Successfully connected to MongoDB database: {db_name}")
            self._connected = True
            return self.database

        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")
            self._connected = False
            raise

    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            print("Disconnected from MongoDB")
        self._connected = False
        self.client = None
        self.database = None


# Global database client instance
db_client = DatabaseClient()


def get_db() -> Database:
    """
    FastAPI dependency to get database connection
    """
    return db_client.connect()
