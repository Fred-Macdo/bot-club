
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

# Setup paths (adjust these based on where you run the script from)
# If running from app/ root:
env_path = Path("backend/.env")
# If running from backend/ root:
# env_path = Path(".env")

print(f"Loading env from: {env_path.absolute()}")
load_dotenv(dotenv_path=env_path)

MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "bot_club_db")

print(f"Connecting to: {MONGO_URL} (DB: {MONGO_DB_NAME})")

try:
    client = MongoClient(MONGO_URL)
    db = client[MONGO_DB_NAME]
    
    # Test connection
    client.admin.command('ping')
    print("✓ Connected to MongoDB successfully!")
    
    # List collections
    collections = db.list_collection_names()
    print(f"\nCollections found: {collections}")
    
    # 1. Check User Configs
    print("\n--- Checking User Configs ---")
    user_config_count = db.user_config.count_documents({})
    print(f"Total User Configs: {user_config_count}")
    
    sample_config = db.user_config.find_one()
    if sample_config:
        print(f"Sample User Config (ID: {sample_config.get('_id')}):")
        # Print non-sensitive keys
        print({k: v for k, v in sample_config.items() if 'key' not in k and 'secret' not in k})
        user_id = sample_config.get('user_id')
        print(f"-> Linked User ID: {user_id}")
    else:
        print("No user configs found.")

    # 2. Check Strategies
    print("\n--- Checking User Strategies ('strategy') ---")
    strategy_count = db.strategy.count_documents({})
    print(f"Total User Strategies: {strategy_count}")
    
    strategies = list(db.strategy.find().limit(5))
    for s in strategies:
        print(f"- [ID: {s.get('_id')}] Name: {s.get('name')}, User: {s.get('user_id')}")

    # 3. Check Default Strategies
    print("\n--- Checking Default Strategies ('default_strategies') ---")
    default_count = db.default_strategies.count_documents({})
    print(f"Total Default Strategies: {default_count}")
    
    defaults = list(db.default_strategies.find().limit(5))
    for s in defaults:
        print(f"- [ID: {s.get('_id')}] Name: {s.get('name')}")

except Exception as e:
    print(f"\n✗ Error: {e}")
    print("Ensure you are forwarding the Mongo port (27017) or running this inside the container.")
