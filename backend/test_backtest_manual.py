import os
import sys
import logging
from pymongo import MongoClient

# Add current directory to path so we can import src
sys.path.append(os.getcwd())

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock keys to avoid import errors from missing env vars
os.environ["MONGO_URL"] = "mongodb://localhost:27017/"
os.environ["MONGO_DB_NAME"] = "bot_club_db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

try:
    from src.tasks.backtest_task import run_backtest_task
except ImportError as e:
    logger.error(f"Import failed: {e}")
    logger.info("Make sure you run this script from the 'app/backend' directory.")
    sys.exit(1)

def test_task():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("MONGO_DB_NAME")
    
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
    try:
        client.server_info() # Check connection
    except Exception as e:
        logger.error(f"Could not connect to MongoDB: {e}")
        # We can't proceed without DB
        # But for 'testing the script' logic, maybe we can mock the DB calls if we can't connect?
        # Given this is likely a dev environment without a live mongo reachable from THIS terminal 
        # (the user is on Windows, containers might be running but 'mongo' hostname connects only inside docker network),
        # we might need to use localhost if ports are exposed.
        logger.info("Trying localhost for Mongo...")
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    
    db = client[db_name]

    # Find a user
    user = db.users.find_one()
    if not user:
        logger.warning("No users found in DB. Creating a temporary test user.")
        user_id = db.users.insert_one({"username": "test_user", "encryption_key": "dummy_key"}).inserted_id
    else:
        user_id = user["_id"]

    # Find a strategy
    strategy = db.strategies.find_one({"user_id": user_id})
    if not strategy:
        logger.warning("No strategies found for user. Creating a temporary test strategy.")
        strategy_id = db.strategies.insert_one({
            "user_id": user_id, 
            "name": "Test Strategy", 
            "symbols": ["AAPL"], 
            "type": "custom"
        }).inserted_id
    else:
        strategy_id = strategy["_id"]

    logger.info(f"Testing with User ID: {user_id}, Strategy ID: {strategy_id}")

    # Prepare payload
    payload = {
        "strategy_id": str(strategy_id),
        "initial_capital": 10000.0,
        "timeframe": "1D",
        "start_date": "2023-01-01",
        "end_date": "2023-01-31",
        "data_provider": "yahoo", # 'yahoo' usually works without keys
        "strategy_type": "custom" # Extra field to check filtering
    }

    logger.info("Invoking task synchronously...")
    
    # We call the function directly (bypassing Celery worker)
    # The 'self' argument is usually injected by Celery, but if we call the decorated function, 
    # we might need to mock 'self', OR the undecorated function is not easily accessible.
    # Celery tasks are callable. calling task() usually calls the body.
    try:
        # Note: calling 'run_backtest_task(payload, str(user_id))' might fail if 'bind=True' expects 'self'.
        # With bind=True, the first argument 'self' is passed automatically if called via apply/delay.
        # If called directly: run_backtest_task(backtest_request_data=payload, user_id=str(user_id))
        # Celery 4/5 usually handles this gracefully if not relying on 'self' internals too much.
        
        # But wait, run_backtest_task uses 'bind=True', so the first argument IS 'self'.
        # We can construct a mock self if needed, or rely on .apply()
        
        class MockTask:
            request = type('obj', (object,), {'id': 'test-task-id'})
            
        # Or even better, just invoke it with .apply() which runs it locally
        result = run_backtest_task.apply(args=[payload, str(user_id)])
        
        logger.info(f"Task executed. Result: {result.result}")
        if result.status == 'SUCCESS':
            logger.info("Test PASSED.")
        else:
            logger.error(f"Test FAILED with status {result.status}")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_task()
