from datetime import datetime
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from bson import ObjectId
import asyncio

from ...models.backtest import BacktestParams
from ..trading.alpaca_trading_service import AlpacaTradingService
from ..utils.enums import TradingMode

logger = logging.getLogger(__name__)

class TradingService:
    """
    This class is responsible for managing live and paper trading sessions.
    """
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.active_sessions: Dict[str, asyncio.Task] = {}

    async def _get_strategy_from_db(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get strategy from database"""
        try:
            object_id = ObjectId(strategy_id)
        except Exception:
            raise ValueError(f"Invalid strategy_id format: {strategy_id}")

        strategy_doc = await self.db['default_strategies'].find_one({'_id': object_id})
        if strategy_doc is None:
            strategy_doc = await self.db['strategy'].find_one({'_id': object_id})
        
        if strategy_doc is None:
            logger.warning(f"Strategy {strategy_id} not found in default_strategies or strategy collections.")
            return None
        
        return strategy_doc

    async def run_trading(
        self, 
        strategy_id: str, 
        mode: TradingMode,
        user_id: str,
        alpaca_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Unified method to run trading in paper or live mode.
        """
        logger.info(f"Starting {mode.value} trading for strategy: {strategy_id}")
        
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if strategy_id in self.active_sessions and not self.active_sessions[strategy_id].done():
            logger.warning(f"Trading session for strategy {strategy_id} is already running.")
            return {"status": "already_running", "strategy_id": strategy_id}
        
        if mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            
            # A factory here could select the appropriate broker service in the future
            trading_service_instance = AlpacaTradingService(
                db=self.db,
                user_id=user_id,
                mode=mode,
                strategy_id=strategy_id
            )

            session_task = asyncio.create_task(
                trading_service_instance.run(strategy)
            )

            self.active_sessions[strategy_id] = session_task
            return {"status": "started", "strategy_id": strategy_id}
        else:
            raise ValueError(f"Invalid trading mode for this service: {mode}.")

    async def stop_trading(self, strategy_id: str) -> Dict[str, Any]:
        """Stop a trading session."""
        if strategy_id in self.active_sessions:
            task = self.active_sessions[strategy_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Cancellation is expected
                del self.active_sessions[strategy_id]
                logger.info(f"Stopped trading session for strategy {strategy_id}")
                return {"status": "stopped", "strategy_id": strategy_id}
        
        logger.warning(f"No active trading session found to stop for strategy {strategy_id}")
        return {"status": "not_found", "strategy_id": strategy_id}

    async def get_trading_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get the status of a trading session."""
        if strategy_id in self.active_sessions:
            task = self.active_sessions[strategy_id]
            if task.done():
                if task.exception():
                    logger.error(f"Trading session for {strategy_id} failed: {task.exception()}")
                    return {"status": "failed", "error": str(task.exception())}
                return {"status": "finished"}
            return {"status": "running"}
            
        return {"status": "not_found"} 