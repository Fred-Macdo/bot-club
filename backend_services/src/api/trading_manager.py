"""
Manages running trading strategy processes and their log listeners.
"""
import asyncio
import logging
import multiprocessing as mp
from logging.handlers import QueueHandler
from typing import Dict, Any, Optional

from pymongo import AsyncMongoClient
from lumibot.brokers import Alpaca

from config import MONGO_URL, MONGO_DB
from services.trading.trading_service import CryptoStrategy, StockStrategy
from services.data_retrieval.data_providers import AVAILABLE_CRYPTO_ASSETS
from services.utils.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


def run_strategy_process(
    strategy_config: Dict,
    alpaca_config: Dict,
    log_queue: mp.Queue,
    strategy_id: str,
    mongo_url: str,
    mongo_db_name: str,
    user_id: str
):
    """
    Runs a trading strategy in a separate process.
    This function must be at module level for multiprocessing to pickle it.
    """
    try:
        # Create new database connection in this process
        db_client = AsyncMongoClient(mongo_url)
        db = db_client[mongo_db_name]
        
        # Create broker and strategy
        broker = Alpaca(config=alpaca_config)
        logger.info(f"Running strategy: {strategy_config}")
        
        symbols = strategy_config.get('config', {}).get('symbols', [])
        is_crypto = any(symbol in AVAILABLE_CRYPTO_ASSETS for symbol in symbols)
        
        StrategyClass = CryptoStrategy if is_crypto else StockStrategy
        strategy = StrategyClass(
            broker=broker, 
            strategy_config=strategy_config,
            event_queue=log_queue,
            strategy_id=strategy_id,
            db=db,
            user_id=user_id
        )

        # Configure logging to pass logs back to the main process
        queue_handler = QueueHandler(log_queue)
        underlying_logger = strategy.logger.logger
        underlying_logger.addHandler(queue_handler)
        underlying_logger.setLevel(logging.INFO)
        
        # Run the strategy
        strategy.run_live()
    except Exception as e:
        temp_logger = logging.getLogger('process_runner')
        temp_logger.addHandler(QueueHandler(log_queue))
        temp_logger.setLevel(logging.ERROR)
        temp_logger.error(f"Error in strategy process: {e}", exc_info=True)


class TradingManager:
    """
    Manages running trading strategy processes.
    Handles starting, stopping, and monitoring strategies.
    """
    
    def __init__(self):
        self.running_traders: Dict[str, Dict[str, Any]] = {}
    
    def is_running(self, strategy_id: str) -> bool:
        """Check if a strategy is currently running."""
        trader_info = self.running_traders.get(strategy_id)
        return trader_info is not None and trader_info["process"].is_alive()
    
    def get_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get the status of a strategy."""
        if self.is_running(strategy_id):
            return {
                "status": "running",
                "strategy_id": strategy_id,
                "is_running": True
            }
        return {
            "status": "stopped",
            "strategy_id": strategy_id,
            "is_running": False
        }
    
    async def start_strategy(
        self,
        strategy_id: str,
        strategy_config: Dict,
        alpaca_config: Dict,
        user_id: str
    ) -> bool:
        """
        Start a new strategy process.
        Returns True if started successfully, False if already running.
        """
        if strategy_id in self.running_traders:
            logger.warning(f"Strategy {strategy_id} is already running.")
            return False
        
        log_queue = mp.Queue()
        process = mp.Process(
            target=run_strategy_process,
            args=(strategy_config, alpaca_config, log_queue, strategy_id, MONGO_URL, MONGO_DB, user_id)
        )
        process.start()
        
        # Start log listener task
        log_listener_task = asyncio.create_task(
            self._log_listener(strategy_id, log_queue)
        )
        
        self.running_traders[strategy_id] = {
            "process": process,
            "log_queue": log_queue,
            "log_listener_task": log_listener_task
        }
        
        logger.info(f"Started strategy process: {strategy_id}")
        return True
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """
        Stop a running strategy process.
        Returns True if stopped successfully, False if not found/not running.
        """
        trader_info = self.running_traders.get(strategy_id)
        if not trader_info or not trader_info["process"].is_alive():
            return False
        
        # Terminate the process
        trader_info["process"].terminate()
        trader_info["process"].join(timeout=5)
        logger.info(f"Terminated process for strategy {strategy_id}")
        
        # Stop the log listener
        trader_info["log_queue"].put(None)  # Send sentinel
        trader_info["log_listener_task"].cancel()
        
        del self.running_traders[strategy_id]
        return True
    
    async def stop_all(self):
        """Stop all running strategies. Called during shutdown."""
        for strategy_id in list(self.running_traders.keys()):
            trader_info = self.running_traders[strategy_id]
            logger.info(f"Stopping trader for strategy {strategy_id}...")
            
            if trader_info["process"].is_alive():
                trader_info["process"].terminate()
                trader_info["process"].join(timeout=5)
            
            trader_info["log_queue"].put(None)
            trader_info["log_listener_task"].cancel()
        
        self.running_traders.clear()
    
    async def _log_listener(self, strategy_id: str, log_queue: mp.Queue):
        """Listens for log records and events from a strategy process."""
        loop = asyncio.get_running_loop()
        while True:
            try:
                item = await loop.run_in_executor(None, log_queue.get)
                if item is None:  # Sentinel value to stop
                    break
                
                if isinstance(item, dict):
                    # It's an event (trade, position, or metrics)
                    await websocket_manager.broadcast(strategy_id, item)
                else:
                    # It's a LogRecord
                    log_data = {
                        "timestamp": item.created * 1000,
                        "level": item.levelname,
                        "message": item.getMessage()
                    }
                    await websocket_manager.broadcast(strategy_id, {"type": "log", "data": log_data})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log listener for {strategy_id}: {e}", exc_info=True)
        
        logger.info(f"Log listener for strategy {strategy_id} stopped.")


# Singleton instance
trading_manager = TradingManager()
