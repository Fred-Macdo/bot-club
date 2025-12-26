import redis
import json
import logging
import time # Import time for timestamping
from celery_app import celery_app
from config import REDIS_URL, MONGO_URL, MONGO_DB
from services.trading.crypto_strategy import CryptoStrategy
from services.trading.stock_strategy import StockStrategy
from services.data_retrieval.data_providers import AVAILABLE_CRYPTO_ASSETS
from lumibot.brokers import Alpaca
from pymongo import MongoClient

logger = logging.getLogger(__name__)


def publish_to_stream(redis_client, stream_key, event_type, data):
    """Helper function to add data to a Redis Stream with a timestamp."""
    payload = {
        "type": event_type,
        "data_json": json.dumps(data) # Store data as a JSON string within a stream field
    }
    # '*' automatically generates the message ID (timestamp-sequence)
    redis_client.xadd(stream_key, payload, maxlen=1000) # Use maxlen to prevent infinite growth


@celery_app.task(bind=True, time_limit=86400)
def run_live_strategy(self, strategy_config, alpaca_config, strategy_id, user_id):
    """
    Runs a live trading strategy as a Celery task.
    Logs and events are streamed via Redis Streams using the task_id.
    """
    task_id = self.request.id
    # Use task ID for the stream key
    stream_key = f"task:{task_id}" 
    
    # Create Redis client (Sync client for Celery worker)
    redis_client = redis.from_url(REDIS_URL)
    

    # DEBUG: Force publish a test message immediately to verify connectivity
    logger.info(f"DEBUG: Task started. Adding test message to {stream_key}")
    try:
        publish_to_stream(redis_client, stream_key, "log", {
                "timestamp": time.time() * 1000, 
                "level": "INFO", 
                "message": f"DEBUG: Worker started for task {task_id}"
            }
        )
    except Exception as e:
        logger.error(f"DEBUG: Failed to add test message to stream: {e}")

    logger.info(f"Worker started for task {task_id}, publishing to {stream_key}")
    
    try:
        # Publish task started event
        publish_to_stream(redis_client, stream_key, "status", 
                          {"status": "started", "task_id": task_id, "strategy_id": strategy_id})
        logger.info(f"Published start message to {stream_key}")
        
        # Create sync MongoDB connection
        db_client = MongoClient(MONGO_URL)
        db = db_client[MONGO_DB]
        
        # Create broker
        broker = Alpaca(config=alpaca_config)
        
        # Determine if crypto or stock
        symbols = strategy_config.get('config', {}).get('symbols', [])
        logger.info(f"DEBUG Trading Tasks: Strategy symbols: {symbols}")
        is_crypto = any(symbol in AVAILABLE_CRYPTO_ASSETS for symbol in symbols)
        
        # Define stream publisher callback
        def stream_publisher(event_type, data):
            publish_to_stream(redis_client, stream_key, event_type, data)

        if is_crypto:
            strategy = CryptoStrategy(
                broker=broker,
                strategy_config=strategy_config,
                event_queue=None, 
                strategy_id=strategy_id,
                db=db,
                user_id=user_id,
                stream_publisher=stream_publisher
            )
        else:
            strategy = StockStrategy(
                broker=broker,
                strategy_config=strategy_config,
                event_queue=None,
                strategy_id=strategy_id,
                db=db,
                user_id=user_id,
                stream_publisher=stream_publisher
            )
        
        # Note: The original RedisLogHandler needs modification to use xadd instead of publish.
        # For this example, we proceed assuming logging mechanisms are adapted or deferred.
        
        # Run the strategy (blocking call)
        strategy.run_live()
        
        return {"status": "completed", "strategy_id": strategy_id}
        
    except Exception as e:
        logger.error(f"Error in strategy task: {e}", exc_info=True)
        # Publish error event
        publish_to_stream(redis_client, stream_key, "error", {"message": str(e)})
        raise  # Re-raise so Celery marks task as failed
    finally:
        # Publish stopped event
        publish_to_stream(redis_client, stream_key, "status", {"status": "stopped"})
        logger.info(f"Worker stopped for task {task_id}")
        redis_client.close()
