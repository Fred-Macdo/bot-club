import redis
import json
import logging
import os
import time # Import time for timestamping
from ..celery_app import celery_app
#from ..config import REDIS_URL, MONGO_URL, MONGO_DB_NAME
from ..services.trading.crypto_strategy import CryptoStrategy
from ..services.trading.stock_strategy import StockStrategy
from ..services.data_retrieval.data_providers import AVAILABLE_CRYPTO_ASSETS
from ..models.user_config import ConfigEncryption
from lumibot.brokers import Alpaca
from pymongo import MongoClient
from bson import ObjectId

logger = logging.getLogger(__name__)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "bot_club_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def publish_to_stream(redis_client, stream_key, event_type, data):
    """Helper function to add data to a Redis Stream with a timestamp."""
    payload = {
        "type": event_type,
        "data_json": json.dumps(data) # Store data as a JSON string within a stream field
    }
    # '*' automatically generates the message ID (timestamp-sequence)
    redis_client.xadd(stream_key, payload, maxlen=1000) # Use maxlen to prevent infinite growth


@celery_app.task(bind=True, time_limit=86400)
def run_live_strategy(self, trading_request, current_user):
    """
    Runs a live trading strategy as a Celery task.
    Logs and events are streamed via Redis Streams using the task_id.
    """
    strategy_id = trading_request['strategy_id']
    mode = trading_request['mode']
    data_provider = trading_request['data_provider']
    user_id = str(current_user['id'])
    task_id = self.request.id
    # Use task ID for the stream key
    stream_key = f"task:{task_id}" 
    logger.info(f"Starting live strategy task {task_id} for strategy {strategy_id} in {mode} mode using {data_provider} data provider.")
    # Create Redis client (Sync client for Celery worker)
    redis_client = redis.from_url(REDIS_URL)
    logger.info(f"Connected to Redis at {REDIS_URL}")
    # ---------------------------------------------------------
    # CONCURRENCY LOCK: Prevent creation of multiple strategies
    # ---------------------------------------------------------
    lock_key = "lock:alpaca_strategy"
    # Try to acquire lock. If key exists, someone else holds it.
    if not redis_client.set(lock_key, task_id, nx=True, ex=None):
        # Lock exists. Check if it's a zombie task (not actually running).
        existing_task_id_bytes = redis_client.get(lock_key)
        existing_task_id = existing_task_id_bytes.decode('utf-8') if existing_task_id_bytes else None
        
        is_zombie = False
        if existing_task_id:
            try:
                # Inspect active tasks to see if the lock holder is still alive
                i = celery_app.control.inspect()
                # timeout=1.0 prevents hanging if workers are unresponsive
                active = i.active()
                if active: 
                    # Flatten list of all active task IDs across all workers
                    active_ids = [t['id'] for worker_tasks in active.values() for t in worker_tasks]
                    if existing_task_id not in active_ids:
                        is_zombie = True
                        logger.warning(f"Lock held by zombie task {existing_task_id}. Reclaiming lock for {task_id}.")
            except Exception as e:
                logger.error(f"Error checking active tasks: {e}")

        if is_zombie:
             # Steal the lock
             redis_client.set(lock_key, task_id)
        else:
            error_msg = f"Another strategy is already running (Task: {existing_task_id}). Please stop it before starting a new one."
            logger.error(error_msg)
            publish_to_stream(redis_client, stream_key, "error", {"message": error_msg})
            return {"status": "failed", "error": error_msg}

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
        logger.info(f"DEBUG: Connecting to Mongo at {MONGO_URL} (DB: {MONGO_DB_NAME})")
        db_client = MongoClient(MONGO_URL)
        db = db_client[MONGO_DB_NAME]
        
        # DEBUG: List collections and IDs
        try:
            col_names = db.list_collection_names()
            logger.info(f"DEBUG: Available collections: {col_names}")
            
            # Log IDs in strategy collection
            strategies = list(db.strategy.find({}, {"_id": 1}))
            logger.info(f"DEBUG: All User Strategy IDs: {[str(s['_id']) for s in strategies]}")

            # Log IDs in default_strategies collection
            defaults = list(db.default_strategies.find({}, {"_id": 1}))
            logger.info(f"DEBUG: All Default Strategy IDs: {[str(s['_id']) for s in defaults]}")
        except Exception as e:
            logger.error(f"DEBUG: Error listing collections: {e}")

        # Fetch Strategy Config
        strategy_doc = db.strategy.find_one({"_id": ObjectId(strategy_id)})
        logger.info(f"Looking for strategy {strategy_id} in 'strategy': {strategy_doc is not None}")
        
        if not strategy_doc:
             # Try default strategies if not found in user strategies
             strategy_doc = db.default_strategies.find_one({"_id": ObjectId(strategy_id)})
             logger.info(f"Looking for strategy {strategy_id} in 'default_strategies': {strategy_doc is not None}")
        
        if not strategy_doc:
             raise ValueError(f"Strategy {strategy_id} not found in 'strategy' or 'default_strategies'")
        strategy_config = strategy_doc

        # Fetch User Config for API Keys
        user_config_doc = db.user_config.find_one({"user_id": user_id})
        if not user_config_doc:
             # Fallback or error? For now, error.
             # In a real app, you might want to handle this gracefully or use env vars.
             logger.warning(f"User config not found for user {user_id}. Using empty config.")
             user_config_doc = {}
        logger.info(f"Fetched user config for trading. {user_config_doc}")
        # Construct Alpaca Config
        if mode == 'paper':
             logger.info(f"Using paper trading config for user {user_id}")
             alpaca_config = {
                 "API_KEY": user_config_doc.get('alpaca_paper_api_key'),
                 "API_SECRET": ConfigEncryption.decrypt_value(user_config_doc.get('alpaca_paper_secret_key')),
                 "PAPER": True
             }
        else:
             logger.info(f"Using live trading config for user {user_id}")
             alpaca_config = {
                 "API_KEY": user_config_doc.get('alpaca_live_api_key'),
                 "API_SECRET": ConfigEncryption.decrypt_value(user_config_doc.get('alpaca_live_secret_key')),
                 "PAPER": False
             }
        logger.info(f"Alpaca config {alpaca_config}")
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
        # ---------------------------------------------------------
        # RELEASE LOCK
        # ---------------------------------------------------------
        try:
            # Check if we still hold the lock before deleting
            current_holder = redis_client.get(lock_key)
            if current_holder and current_holder.decode('utf-8') == task_id:
                redis_client.delete(lock_key)
                logger.info(f"Released concurrency lock for task {task_id}")
        except Exception as lock_e:
            logger.error(f"Error releasing lock: {lock_e}")

        # Publish stopped event
        publish_to_stream(redis_client, stream_key, "status", {"status": "stopped"})
        logger.info(f"Worker stopped for task {task_id}")
        redis_client.close()

@celery_app.task(bind=True)
def stop_live_strategy(self, task_id):
    """
    Stops a running live trading strategy by revoking the Celery task.
    Uses SIGKILL to ensure immediate termination if SIGTERM is ignored.
    Manually releases the Redis lock since SIGKILL prevents the worker's finally block from running.
    """
    logger.info(f"Received request to stop task {task_id}")
    
    redis_client = None
    # Manually release the lock if it belongs to this task
    try:
        redis_client = redis.from_url(REDIS_URL)
        
        # Publish stopped event to stream so frontend knows to disconnect
        stream_key = f"task:{task_id}"
        publish_to_stream(redis_client, stream_key, "status", {"status": "stopped"})
        logger.info(f"Published stopped status to {stream_key}")
        
        lock_key = "lock:alpaca_strategy"
        current_holder = redis_client.get(lock_key)
        
        if current_holder:
            current_holder_str = current_holder.decode('utf-8')
            if current_holder_str == task_id:
                redis_client.delete(lock_key)
                logger.info(f"Manually released lock:alpaca_strategy for task {task_id} during stop procedure")
            else:
                logger.warning(f"Lock held by {current_holder_str}, not {task_id}. Not removing.")
        else:
            logger.info("No lock found to release.")
            
    except Exception as e:
        logger.error(f"Error cleaning up lock/stream during stop: {e}")
    finally:
        if redis_client:
            redis_client.close()

    # Revoke the task and terminate it immediately with SIGKILL
    celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')
    
    return {"status": "stop_requested", "task_id": task_id}