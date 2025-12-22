"""
Manages running trading strategy tasks via Celery and listens for their logs via Redis.
"""
import asyncio
import logging
import json
import redis.asyncio as aioredis
from typing import Dict, Any, Optional
import uuid
from celery.result import AsyncResult
from redis import Redis

# Import config and app
from config import REDIS_URL
from celery_app import celery_app
# Import the Celery task
from services.tasks.trading_tasks import run_live_strategy
from services.utils.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class CeleryTradingManager:
    """
    Manages running trading strategies via Celery.
    Handles starting tasks, stopping (revoking) tasks, and streaming logs from Redis.
    """
    
    def __init__(self):
        # Maps strategy_id -> { "task_id": str, "listener_task": asyncio.Task }
        self.running_traders: Dict[str, Dict[str, Any]] = {}
        self.redis_client: Optional[aioredis.Redis] = None

        # Sync Redis client for management operations
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)

    async def initialize(self):
        """Initialize Redis connection for log listening."""
        if not self.redis_client:
            self.redis_client = await aioredis.from_url(REDIS_URL)
            logger.info("CeleryTradingManager connected to Redis")

    async def shutdown(self):
        """Cleanup resources."""
        await self.stop_all()
        if self.redis_client:
            await self.redis_client.close()
            logger.info("CeleryTradingManager disconnected from Redis")

    def is_running(self, strategy_id: str) -> bool:
        """Check if a strategy task is currently running."""
        trader_info = self.running_traders.get(strategy_id)
        if not trader_info:
            return False
        
        task_id = trader_info["task_id"]
        result = AsyncResult(task_id, app=celery_app)
        # Check if task is in a running state (PENDING, STARTED, or RETRY)
        return result.status in ['PENDING', 'STARTED', 'RETRY']

    def get_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get the status of a strategy."""
        trader_info = self.running_traders.get(strategy_id)
        if trader_info:
            task_id = trader_info["task_id"]
            result = AsyncResult(task_id, app=celery_app)
            return {
                "status": result.status,
                "strategy_id": strategy_id,
                "task_id": task_id,
                "is_running": result.status in ['PENDING', 'STARTED', 'RETRY']
            }
        
        return {
            "status": "stopped",
            "strategy_id": strategy_id,
            "is_running": False
        }

    def start_strategy(
        self,
        strategy_id: str,
        strategy_config: Dict,
        alpaca_config: Dict,
        user_id: str
    ) -> bool:
        """
        Start a new strategy Celery task.
        Returns True if started successfully, False if already running.
        """
        if self.is_running(strategy_id):
            return False
          
        # Determine queue based on paper trading setting
        is_paper = alpaca_config.get('PAPER', True)
        queue_name = 'paper_trading' if is_paper else 'live_trading'

        # Start Celery task
        task_func = run_live_strategy
        task = task_func.apply_async(
            args=(strategy_config, alpaca_config, strategy_id, user_id),
            task_id=f"strategy-{strategy_id}",
            queue=queue_name
        )
        
        # Add debug logging
        logger.info(f"DEBUG: Dispatched Celery task {task.id} for strategy {strategy_id} on queue {queue_name}")
        logger.info(f"DEBUG: Task state: {task.state}")
        
        # Start Redis log listener for this strategy
        # NOTE: With WebSocketManager now listening to task:{task_id} directly, 
        # we might not need this listener if the frontend connects via task_id.
        # But if the frontend connects via strategy_id (legacy), we need a bridge.
        # However, run_live_strategy publishes to task:{task_id}.
        # So strategy:{strategy_id} channel receives nothing unless we double-publish.
        # 
        # The frontend IS connecting via task_id now (see DeployedStrategyContext.js changes).
        # The backend WebSocketHandler uses WebSocketManager which subscribes to task:{task_id}.
        # So the flow is:
        # Worker -> Redis (task:{task_id}) -> WebSocketManager -> WebSocket -> Frontend
        #
        # This listener below subscribes to strategy:{strategy_id} which is EMPTY.
        # We can remove it or keep it as a no-op placeholder.
        # Removing the task creation to save resources.
        
        # listener_task = asyncio.create_task(
        #     self._redis_log_listener(strategy_id)
        # )
        
        self.running_traders[strategy_id] = {
            "task_id": task.id,
            # "listener_task": listener_task 
        }
        
        logger.info(f"Started strategy task {task.id} for {strategy_id} on queue {queue_name}")
        return True

    def stop_strategy(self, strategy_id: str) -> bool:
        """
        Stop a running strategy task.
        Returns True if stopped successfully.
        """
        trader_info = self.running_traders.get(strategy_id)
        if not trader_info:
            return False
            
        task_id = trader_info["task_id"]
        
        # Revoke Celery task with terminate=True to send SIGTERM to the worker process
        celery_app.control.revoke(task_id, terminate=True)
        logger.info(f"Revoked task {task_id} for strategy {strategy_id}")
        
        # Stop listener if it exists
        if "listener_task" in trader_info and trader_info["listener_task"]:
            trader_info["listener_task"].cancel()
            logger.info(f"Log listener cancelled for {strategy_id}")
            
        del self.running_traders[strategy_id]
        return True

    async def stop_all(self):
        """Stop all running strategies. Called during shutdown."""
        for strategy_id in list(self.running_traders.keys()):
            await self.stop_strategy(strategy_id)
        self.running_traders.clear()


# Singleton instance
celery_trading_manager = CeleryTradingManager()
