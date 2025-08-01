import asyncio
import logging
from typing import Dict, Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..utils.enums import TradingMode
from ..utils.live_strategy_executor import LiveStrategyExecutor

logger = logging.getLogger(__name__)

class TradingService:
    """Manages live and paper trading sessions."""
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.live_executors: Dict[str, LiveStrategyExecutor] = {}

    async def start_trading_session(self, strategy_id: str, user_id: str, mode: TradingMode, data_provider: str):
        """Starts a new trading session (live or paper)."""
        if strategy_id in self.live_executors and self.live_executors[strategy_id].is_running:
            logger.warning(f"DEBUG TRADING SERVICE: Strategy {strategy_id} is already running.")
            return {"status": "already_running", "strategy_id": strategy_id}

        strategy_doc = await self.get_strategy_by_id(strategy_id)
        if not strategy_doc:
            logger.error(f"DEBUG TRADING SERVICE: Strategy {strategy_id} not found.")
            return {"status": "not_found", "strategy_id": strategy_id}

        logger.info(f"DEBUG TRADING SERVICE: Starting {mode.value} trading for strategy: {strategy_id}")
        executor = LiveStrategyExecutor(
            db=self.db,
            user_id=user_id,
            mode=mode,
            strategy=strategy_doc,
            strategy_id=strategy_id,
            data_provider=data_provider
        )
        self.live_executors[strategy_id] = executor

        # Run the executor in a background task
        asyncio.create_task(executor.start())
        
        return {"status": "started", "strategy_id": strategy_id}

    async def stop_trading_session(self, strategy_id: str):
        """Stops a running trading session and waits for it to terminate."""
        executor = self.live_executors.get(strategy_id)
        
        if executor and executor.is_running:
            logger.info(f"Stopping trading session for strategy: {strategy_id}")
            
            # Signal the executor to stop
            await executor.stop()
            
            # Optionally, wait for the task to complete if `stop` doesn't block
            # This depends on the implementation of `LiveStrategyExecutor.stop()`
            # For now, we assume `stop` is asynchronous and handles cleanup.
            
            # Remove the executor from the active list
            if strategy_id in self.live_executors:
                del self.live_executors[strategy_id]
            
            logger.info(f"Successfully stopped and removed executor for strategy: {strategy_id}")
            return {"status": "stopped", "strategy_id": strategy_id}
        
        logger.warning(f"Attempted to stop a non-running or non-existent strategy: {strategy_id}")
        return {"status": "not_running", "strategy_id": strategy_id}

    def get_trading_session_status(self, strategy_id: str):
        """Gets the status of a trading session."""
        if strategy_id in self.live_executors:
            is_running = self.live_executors[strategy_id].is_running
            return {"status": "running" if is_running else "stopped", "strategy_id": strategy_id}
        return {"status": "not_found", "strategy_id": strategy_id}

    async def shutdown(self):
        """Shuts down all running trading sessions."""
        logger.info("Shutting down all active trading sessions...")
        for executor in self.live_executors.values():
            if executor.is_running:
                await executor.stop()
        self.live_executors.clear()
        logger.info("All trading sessions stopped.") 

    async def get_strategy_by_id(self, strategy_id: str):
        """Gets a strategy by its ID. Tries default_strategies first, then strategies collection."""
        try:
            strategy_doc = await self.db.default_strategies.find_one({"_id": ObjectId(strategy_id)})
            if not strategy_doc:
                strategy_doc = await self.db.strategy.find_one({"_id": ObjectId(strategy_id)})
            return strategy_doc
        except Exception as e:
            logger.error(f"Error getting strategy by ID: {e}")
            return None
        