import asyncio
import os
import sys
import yaml
from pathlib import Path
from datetime import datetime, timezone

# Add the src directory to Python path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from database.client import db_client
from services.default_strategies import get_default_strategies
from models.strategy import Strategy
from utils.mongo_helpers import PyObjectId
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def initialize_default_strategies_collection():
    """Initialize the default_strategies collection with YAML strategies"""
    try:
        db = db_client.get_database()
        
        # Clear existing default strategies
        await db.default_strategies.delete_many({})
        logger.info("Cleared existing default strategies")
        
        # Get the data directory path (backend/data/)
        current_dir = Path(__file__).parent.parent.parent  # Go up to backend/
        data_dir = current_dir / 'data'
        
        # List of default strategy YAML files
        strategy_files = [
            'ema_crossover_strategy.yaml',
            'bollinger_bands_strategy.yaml',
            'macd_momentum_strategy.yaml'
        ]
        
        loaded_count = 0
        for filename in strategy_files:
            yaml_path = data_dir / filename
            if yaml_path.exists():
                try:
                    with open(yaml_path, 'r', encoding='utf-8') as file:
                        strategy_data = yaml.safe_load(file)
                    
                    # Add metadata for the default strategy
                    default_strategy_doc = {
                        "_id": PyObjectId(),
                        "template_name": strategy_data['name'],
                        "template_description": strategy_data.get('description', ''),
                        "yaml_config": strategy_data,
                        "created_at": datetime.now(tz=timezone.utc),
                        "updated_at": datetime.now(tz=timezone.utc)
                    }
                    
                    result = await db.default_strategies.insert_one(default_strategy_doc)
                    logger.info(f"Loaded default strategy: {strategy_data['name']} with ID: {result.inserted_id}")
                    loaded_count += 1
                    
                except Exception as e:
                    logger.error(f"Error loading strategy from {filename}: {e}")
            else:
                logger.warning(f"Strategy file not found: {yaml_path}")
        
        logger.info(f"Successfully loaded {loaded_count} default strategies into collection")
        return loaded_count
        
    except Exception as e:
        logger.error(f"Failed to initialize default strategies collection: {e}")
        raise

async def initialize_database():
    """Initialize the database with default data"""
    try:
        # Connect to database
        await db_client.connect()
        db = db_client.get_database()
        
        # Check if we have any collections
        collections = await db.list_collection_names()
        logger.info(f"Existing collections: {collections}")
        
        # Initialize default strategies collection
        logger.info("Initializing default strategies collection...")
        await initialize_default_strategies_collection()
        
        # Create a test user if none exist
        user_count = await db.user.count_documents({})
        if user_count == 0:
            logger.info("Creating test user...")
            test_user = {
                "_id": PyObjectId(),
                "email": "test@example.com",
                "username": "testuser",
                "hashed_password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewgmNDqh.EKTjg6m",  # password: "testpass"
                "is_active": True,
                "created_at": datetime.now(tz=timezone.utc)
            }
            await db.user.insert_one(test_user)
            logger.info(f"Created test user with ID: {test_user['_id']}")
            
            # Create default strategies for test user from the default collection
            await create_user_strategies_from_defaults(db, test_user["_id"])
        
        # Verify collections were created
        collections_after = await db.list_collection_names()
        logger.info(f"Collections after initialization: {collections_after}")
        
        # Show document counts
        for collection_name in collections_after:
            count = await db[collection_name].count_documents({})
            logger.info(f"Collection '{collection_name}' has {count} documents")
            
            # Show sample documents (limit output for readability)
            if count > 0:
                sample = await db[collection_name].find_one()
                # Only show limited fields for large documents
                if collection_name == 'default_strategies':
                    logger.info(f"Sample from '{collection_name}': {sample['template_name']} - {sample['template_description']}")
                else:
                    logger.info(f"Sample document from '{collection_name}': {sample}")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        await db_client.disconnect()

async def create_user_strategies_from_defaults(db, user_id: PyObjectId):
    """Create user strategies from the default_strategies collection"""
    try:
        # Get all default strategies
        default_strategies_cursor = db.default_strategies.find({})
        created_count = 0
        
        async for default_strategy in default_strategies_cursor:
            yaml_config = default_strategy['yaml_config']
            
            # Create strategy document for the user
            strategy_doc = {
                "_id": PyObjectId(),
                "user_id": user_id,
                "name": yaml_config['name'],
                "description": yaml_config.get('description', ''),
                "config": yaml_config,  # Store the entire YAML config
                "is_active": False,
                "is_paper": True,
                "created_at": datetime.now(tz=timezone.utc),
                "updated_at": datetime.now(tz=timezone.utc)
            }
            
            result = await db.strategy.insert_one(strategy_doc)
            logger.info(f"Created user strategy: {yaml_config['name']} with ID: {result.inserted_id}")
            created_count += 1
        
        logger.info(f"Created {created_count} strategies for user {user_id}")
        return created_count
        
    except Exception as e:
        logger.error(f"Failed to create user strategies from defaults: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(initialize_database())