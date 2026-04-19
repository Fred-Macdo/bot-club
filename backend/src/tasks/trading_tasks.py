import redis
import json
import logging
import os
import time
from datetime import datetime, timezone
from ..celery_app import celery_app
from ..services.data_retrieval.data_providers import (
    AVAILABLE_CRYPTO_ASSETS,
    AlpacaProvider,
)
from ..services.trading.alpaca_client import AlpacaTradingClient
from ..services.trading.live_strategy_runner import LiveStrategyRunner
from ..models.user_config import ConfigEncryption
from ..models.trading_session import (
    TradingSession,
    TradingSessionStatus,
    TradingSessionConfig,
)
from ..utils.asset_classifier import classify_asset_type
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
        "data_json": json.dumps(
            data
        ),  # Store data as a JSON string within a stream field
    }
    # '*' automatically generates the message ID (timestamp-sequence)
    redis_client.xadd(
        stream_key, payload, maxlen=1000
    )  # Use maxlen to prevent infinite growth


@celery_app.task(bind=True, soft_time_limit=82800, time_limit=86400)
def run_live_strategy(self, trading_request, current_user):
    """
    Runs a live trading strategy as a Celery task.
    Logs and events are streamed via Redis Streams using the task_id.
    """
    strategy_id = trading_request["strategy_id"]
    mode = trading_request["mode"]
    data_provider = trading_request["data_provider"].lower()
    initial_capital = trading_request.get("initial_capital", 100000.0)
    extended_hours = trading_request.get("extended_hours", False)
    user_id = str(current_user["id"])
    task_id = self.request.id
    # Use task ID for the stream key
    stream_key = f"task:{task_id}"
    logger.info(
        f"Starting live strategy task {task_id} for strategy {strategy_id} in {mode} mode using {data_provider} data provider."
    )
    # Create Redis client (Sync client for Celery worker)
    redis_client = redis.from_url(REDIS_URL)
    logger.info(f"Connected to Redis at {REDIS_URL}")
    # ---------------------------------------------------------
    # CONCURRENCY LOCK: Prevent multiple strategies per user
    # ---------------------------------------------------------
    lock_key = f"lock:alpaca_strategy:{user_id}:{mode}"
    # Try to acquire lock. If key exists, someone else holds it.
    if not redis_client.set(
        lock_key, task_id, nx=True, ex=86400
    ):  # 24h TTL prevents permanent deadlock
        # Lock exists. Check if it's a zombie task (not actually running).
        existing_task_id_bytes = redis_client.get(lock_key)
        existing_task_id = (
            existing_task_id_bytes.decode("utf-8") if existing_task_id_bytes else None
        )

        is_zombie = False
        if existing_task_id:
            try:
                # Inspect active tasks to see if the lock holder is still alive
                i = celery_app.control.inspect()
                # timeout=1.0 prevents hanging if workers are unresponsive
                active = i.active()
                if active:
                    # Flatten list of all active task IDs across all workers
                    active_ids = [
                        t["id"]
                        for worker_tasks in active.values()
                        for t in worker_tasks
                    ]
                    if existing_task_id not in active_ids:
                        is_zombie = True
                        logger.warning(
                            f"Lock held by zombie task {existing_task_id}. Reclaiming lock for {task_id}."
                        )
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
        publish_to_stream(
            redis_client,
            stream_key,
            "log",
            {
                "timestamp": time.time() * 1000,
                "level": "INFO",
                "message": f"DEBUG: Worker started for task {task_id}",
            },
        )
    except Exception as e:
        logger.error(f"DEBUG: Failed to add test message to stream: {e}")

    logger.info(f"Worker started for task {task_id}, publishing to {stream_key}")

    session_id = None
    db_client_conn = None
    try:
        # Publish task started event
        publish_to_stream(
            redis_client,
            stream_key,
            "status",
            {"status": "started", "task_id": task_id, "strategy_id": strategy_id},
        )
        logger.info(f"Published start message to {stream_key}")

        # Create sync MongoDB connection
        logger.info(f"Connecting to Mongo at {MONGO_URL} (DB: {MONGO_DB_NAME})")
        db_client_conn = MongoClient(MONGO_URL)
        db = db_client_conn[MONGO_DB_NAME]

        # Fetch Strategy Config
        strategy_doc = db.strategy.find_one({"_id": ObjectId(strategy_id)})
        logger.info(
            f"Looking for strategy {strategy_id} in 'strategy': {strategy_doc is not None}"
        )

        if not strategy_doc:
            strategy_doc = db.default_strategies.find_one(
                {"_id": ObjectId(strategy_id)}
            )
            logger.info(
                f"Looking for strategy {strategy_id} in 'default_strategies': {strategy_doc is not None}"
            )

        if not strategy_doc:
            raise ValueError(
                f"Strategy {strategy_id} not found in 'strategy' or 'default_strategies'"
            )
        strategy_config = strategy_doc

        # Fetch User Config for API Keys
        user_config_doc = db.user_config.find_one({"user_id": user_id})
        if not user_config_doc:
            logger.warning(
                f"User config not found for user {user_id}. Using empty config."
            )
            user_config_doc = {}

        # Construct Alpaca credentials
        if mode == "paper":
            logger.info(f"Using paper trading config for user {user_id}")
            api_key = user_config_doc.get("alpaca_paper_api_key")
            secret_key = ConfigEncryption.decrypt_value(
                user_config_doc.get("alpaca_paper_secret_key")
            )
            is_paper = True
        else:
            logger.info(f"Using live trading config for user {user_id}")
            api_key = user_config_doc.get("alpaca_live_api_key")
            secret_key = ConfigEncryption.decrypt_value(
                user_config_doc.get("alpaca_live_secret_key")
            )
            is_paper = False

        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca API credentials not configured. Please set them in your account settings."
            )

        # Create Alpaca clients
        alpaca_trading = AlpacaTradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=is_paper,
        )
        alpaca_data = AlpacaProvider(
            api_key=api_key,
            secret_key=secret_key,
        )

        # Determine if crypto or stock
        symbols = strategy_config.get("config", {}).get("symbols", [])
        logger.info(f"Strategy symbols: {symbols}")
        try:
            asset_type = classify_asset_type(symbols)
        except ValueError:
            # Fallback for legacy strategies: check first symbol
            asset_type = (
                "crypto"
                if any(s in AVAILABLE_CRYPTO_ASSETS for s in symbols)
                else "stock"
            )
        is_crypto = asset_type == "crypto"

        # Build schedule_name for stock strategies (matches route-created entry)
        schedule_name = None
        if not is_crypto:
            schedule_name = f"redbeat:stock:{user_id}:{strategy_id}:{mode}"

        # Create or resume TradingSession
        strategy_name = strategy_config.get("name", "Unnamed Strategy")
        timeframe = strategy_config.get("config", {}).get("timeframe", "15M")

        session = TradingSession(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            user_id=user_id,
            task_id=task_id,
            config=TradingSessionConfig(
                mode=mode,
                data_provider=data_provider,
                initial_capital=initial_capital,
                timeframe=timeframe,
                symbols=symbols,
                asset_type=asset_type,
                extended_hours=extended_hours,
                schedule_name=schedule_name,
            ),
            strategy_config=strategy_config.get("config", {}),
            status=TradingSessionStatus.ACTIVE,
            started_at=datetime.now(tz=timezone.utc),
        )
        session_id = session.session_id

        # Upsert session (replace any previous session for this strategy+user+mode)
        db.trading_sessions.update_one(
            {"strategy_id": strategy_id, "user_id": user_id, "config.mode": mode},
            {"$set": session.model_dump(mode="json")},
            upsert=True,
        )
        logger.info(f"Trading session created: {session_id}")

        # Define stream publisher callback
        def stream_publisher(event_type, data):
            publish_to_stream(redis_client, stream_key, event_type, data)

        # Create the unified strategy runner
        runner = LiveStrategyRunner(
            alpaca_client=alpaca_trading,
            data_provider=alpaca_data,
            strategy_config=strategy_config,
            strategy_id=strategy_id,
            user_id=user_id,
            db=db,
            stream_publisher=stream_publisher,
            initial_capital=initial_capital,
            session_id=session_id,
            is_crypto=is_crypto,
            extended_hours=extended_hours,
            mode=mode,
        )

        # Run the strategy (blocking loop — exits when stopped or error)
        runner.run()

        # Determine post-run status:
        # - Stock strategies that exit at market close → SCHEDULED (Beat restarts)
        # - Everything else → COMPLETED
        if runner._exited_market_hours:
            post_status = TradingSessionStatus.SCHEDULED
        else:
            post_status = TradingSessionStatus.COMPLETED

        db.trading_sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": post_status,
                    "stopped_at": datetime.now(tz=timezone.utc),
                    "updated_at": datetime.now(tz=timezone.utc),
                }
            },
        )

        return {
            "status": post_status,
            "strategy_id": strategy_id,
            "session_id": session_id,
        }

    except Exception as e:
        logger.error(f"Error in strategy task: {e}", exc_info=True)
        publish_to_stream(redis_client, stream_key, "error", {"message": str(e)})

        # Mark session as error
        if session_id:
            try:
                db = db_client_conn[MONGO_DB_NAME] if db_client_conn else None
                if db:
                    db.trading_sessions.update_one(
                        {"session_id": session_id},
                        {
                            "$set": {
                                "status": TradingSessionStatus.ERROR,
                                "error_message": str(e),
                                "stopped_at": datetime.now(tz=timezone.utc),
                                "updated_at": datetime.now(tz=timezone.utc),
                            }
                        },
                    )
            except Exception:
                pass

        raise
    finally:
        # ---------------------------------------------------------
        # RELEASE LOCK
        # ---------------------------------------------------------
        try:
            current_holder = redis_client.get(lock_key)
            if current_holder and current_holder.decode("utf-8") == task_id:
                redis_client.delete(lock_key)
                logger.info(f"Released concurrency lock for task {task_id}")
        except Exception as lock_e:
            logger.error(f"Error releasing lock: {lock_e}")

        # Publish stopped event
        publish_to_stream(redis_client, stream_key, "status", {"status": "stopped"})
        logger.info(f"Worker stopped for task {task_id}")
        redis_client.close()

        if db_client_conn:
            db_client_conn.close()


@celery_app.task(bind=True)
def stop_live_strategy(self, task_id):
    """
    Stops a running live trading strategy by revoking the Celery task.
    Uses SIGKILL to ensure immediate termination if SIGTERM is ignored.
    Manually releases the Redis lock since SIGKILL prevents the worker's finally block from running.
    Also marks the TradingSession as stopped in MongoDB.
    """
    logger.info(f"Received request to stop task {task_id}")

    redis_client = None
    db_client_conn = None
    try:
        redis_client = redis.from_url(REDIS_URL)

        # Publish stopped event to stream so frontend knows to disconnect
        stream_key = f"task:{task_id}"
        publish_to_stream(redis_client, stream_key, "status", {"status": "stopped"})
        logger.info(f"Published stopped status to {stream_key}")

        # Look up the session to get user_id for the per-user lock key
        db_client_conn = MongoClient(MONGO_URL)
        db = db_client_conn[MONGO_DB_NAME]
        session_doc = db.trading_sessions.find_one({"task_id": task_id})

        if session_doc and session_doc.get("user_id"):
            session_mode = session_doc.get("config", {}).get("mode", "paper")
            lock_key = f"lock:alpaca_strategy:{session_doc['user_id']}:{session_mode}"
            current_holder = redis_client.get(lock_key)

            if current_holder:
                current_holder_str = current_holder.decode("utf-8")
                if current_holder_str == task_id:
                    redis_client.delete(lock_key)
                    logger.info(
                        f"Manually released {lock_key} for task {task_id} during stop procedure"
                    )
                else:
                    logger.warning(
                        f"Lock {lock_key} held by {current_holder_str}, not {task_id}. Not removing."
                    )
            else:
                logger.info(f"No lock found at {lock_key} to release.")

            # Delete RedBeat schedule entry for stock strategies
            schedule_name = session_doc.get("config", {}).get("schedule_name")
            if schedule_name:
                try:
                    from redbeat import RedBeatSchedulerEntry

                    entry = RedBeatSchedulerEntry.from_key(
                        schedule_name, app=celery_app
                    )
                    entry.delete()
                    logger.info(f"Deleted RedBeat schedule: {schedule_name}")
                except Exception as rb_e:
                    logger.warning(
                        f"Could not delete RedBeat entry {schedule_name}: {rb_e}"
                    )
        else:
            logger.warning(
                f"Could not find session for task {task_id} to determine user_id for lock release."
            )

        # Mark session as stopped in MongoDB
        try:
            result = db.trading_sessions.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": TradingSessionStatus.STOPPED,
                        "stopped_at": datetime.now(tz=timezone.utc),
                        "updated_at": datetime.now(tz=timezone.utc),
                    }
                },
            )
            if result.modified_count:
                logger.info(f"Marked trading session as stopped for task {task_id}")
        except Exception as db_e:
            logger.error(f"Error updating session on stop: {db_e}")

    except Exception as e:
        logger.error(f"Error cleaning up lock/stream during stop: {e}")
    finally:
        if redis_client:
            redis_client.close()
        if db_client_conn:
            db_client_conn.close()

    # Revoke the task and terminate it immediately with SIGKILL
    celery_app.control.revoke(task_id, terminate=True, signal="SIGKILL")

    return {"status": "stop_requested", "task_id": task_id}
