import redis
import json
import logging
from celery_app import celery_app
from config import REDIS_URL, MONGO_URL, MONGO_DB
from services.trading.trading_service import CryptoStrategy, StockStrategy
from services.data_retrieval.data_providers import AVAILABLE_CRYPTO_ASSETS
from lumibot.brokers import Alpaca
from pymongo import MongoClient

logger = logging.getLogger(__name__)

class RedisLogHandler(logging.Handler):
    """Custom logging handler that publishes logs to Redis Pub/Sub."""
    
    def __init__(self, redis_client, channel: str):
        super().__init__()
        self.redis_client = redis_client
        self.channel = channel
    
    def emit(self, record):
        try:
            log_data = {
                "type": "log",
                "data": {
                    "timestamp": record.created * 1000,
                    "level": record.levelname,
                    "message": self.format(record)
                }
            }
            self.redis_client.publish(self.channel, json.dumps(log_data))
        except Exception:
            self.handleError(record)


class RedisEventEmitter:
    """Emits trading events to Redis Pub/Sub instead of multiprocessing Queue."""
    
    def __init__(self, redis_client, channel: str):
        self.redis_client = redis_client
        self.channel = channel
    
    def put(self, event: dict):
        """Mimics queue.put() interface for compatibility with strategy code."""
        try:
            self.redis_client.publish(self.channel, json.dumps(event))
        except Exception as e:
            logger.error(f"Error publishing event to Redis: {e}")


@celery_app.task(bind=True, time_limit=86400)
def run_live_strategy(self, strategy_config, alpaca_config, strategy_id, user_id):
    """
    Runs a live trading strategy as a Celery task.
    Logs and events are streamed via Redis Pub/Sub.
    """
    # Create Redis client for Pub/Sub (Sync client for Celery worker)
    redis_client = redis.from_url(REDIS_URL)
    channel = f"strategy:{strategy_id}"
    
    # Create event emitter that publishes to Redis
    event_emitter = RedisEventEmitter(redis_client, channel)
    
    try:
        # Publish task started event
        redis_client.publish(channel, json.dumps({
            "type": "status",
            "data": {"status": "started", "task_id": self.request.id}
        }))
        
        # Create sync MongoDB connection
        db_client = MongoClient(MONGO_URL)
        db = db_client[MONGO_DB]
        
        # Create broker
        broker = Alpaca(config=alpaca_config)
        
        # Determine if crypto or stock
        symbols = strategy_config.get('config', {}).get('symbols', [])
        is_crypto = any(symbol in AVAILABLE_CRYPTO_ASSETS for symbol in symbols)
        
        if is_crypto:
            strategy = CryptoStrategy(
                broker=broker,
                strategy_config=strategy_config,
                event_queue=event_emitter,  # Redis emitter
                strategy_id=strategy_id,
                db=db,
                user_id=user_id
            )
        else:
            strategy = StockStrategy(
                broker=broker,
                strategy_config=strategy_config,
                event_queue=event_emitter,
                strategy_id=strategy_id,
                db=db,
                user_id=user_id
            )
        
        # Add Redis log handler to the strategy's logger
        redis_handler = RedisLogHandler(redis_client, channel)
        redis_handler.setLevel(logging.INFO)
        redis_handler.setFormatter(logging.Formatter('%(message)s'))
        
        underlying_logger = strategy.logger.logger
        underlying_logger.addHandler(redis_handler)
        underlying_logger.setLevel(logging.INFO)
        
        # Run the strategy (blocking call)
        strategy.run_live()
        
        return {"status": "completed", "strategy_id": strategy_id}
        
    except Exception as e:
        logger.error(f"Error in strategy task: {e}", exc_info=True)
        # Publish error event
        redis_client.publish(channel, json.dumps({
            "type": "error",
            "data": {"message": str(e)}
        }))
        raise  # Re-raise so Celery marks task as failed
    finally:
        redis_client.publish(channel, json.dumps({
            "type": "status",
            "data": {"status": "stopped"}
        }))
        redis_client.close()
