from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
from bson import ObjectId
from pymongo import MongoClient

from ...models.user_config import ConfigEncryption

from ...models.user_config import UserConfigInDB
from ...models.strategy import Strategy
from ...models.backtest import BacktestStatus
from ...utils.mongo_helpers import PyObjectId
from ...tasks.backtest_task import run_backtest_task

import logging

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Orchestrates backtest execution"""
    
    def __init__(self, db):
        """
        Initialize BacktestRunner with async database.
        
        Args:
            db: AsyncMongoClient database instance
        """
        self.db = db
    
    async def run_backtest(
        self,
        user_id: str,
        strategy_id: str,
        initial_capital: float,
        start_date: str,
        end_date: str,
        data_provider: str = "alpaca",
        timeframe: str = "1d"
    ) -> Dict[str, Any]:
        """
        Main entry point for running a backtest.
        
        Args:
            user_id: The user's ID
            strategy_id: The strategy ID to backtest
            initial_capital: Starting capital for the backtest
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            data_provider: Data source (alpaca, polygon, yahoo)
            timeframe: Trading timeframe (1d, 1h, 15m, etc.)
        
        Returns:
            Dict with backtest_id and status
        """
        try:
            # 1. Fetch user API keys (encrypted)
            user_config_doc = self.db.user_config.find_one({"user_id": user_id})

            logger.info(f"Fetched user credentials for backtest: user_id={user_config_doc}")
            if not user_config_doc:
                raise ValueError("User configuration not found")
            
            # 2. Get strategy
            strategy_doc = self.db.strategy.find_one({"_id": ObjectId(strategy_id)})
            logger.info(f"Fetched strategy for backtest: strategy_id={strategy_id}, strategy_doc={strategy_doc}")
            if not strategy_doc:
                raise ValueError("Strategy not found")

            # 4. Prepare payload for Celery task
            task_payload = {
                "backtest_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "strategy_id": str(strategy_id),
                "strategy_config": strategy_doc["config"],
                "initial_capital": initial_capital,
                "start_date": start_date,
                "end_date": end_date,
                "data_provider": data_provider,
                "timeframe": timeframe,
                "encrypted_keys": {
                    "alpaca_live_api_key": user_config_doc.get("alpaca_live_api_key"),
                    "alpaca_live_secret_key": ConfigEncryption.decrypt_value(user_config_doc.get("alpaca_live_secret_key", "")),
                    "polygon_secret_key": ConfigEncryption.decrypt_value(user_config_doc.get("polygon_secret_key", "")),
                }
            }
            logger.info(f"Backtest task payload prepared: {task_payload}")
            
            # 5. Dispatch Celery task
            task = run_backtest_task.delay(task_payload)
            
            return {
                "backtest_id": str(task_payload["backtest_id"]),
                "task_id": task.id,
                "status": "pending",
                "message": "Backtest queued successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to start backtest: {e}")
            raise
    
    async def _get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """Fetch strategy from database"""
        try:
            strategy_doc = await self.db["strategies"].find_one({"_id": ObjectId(strategy_id)})
            if strategy_doc:
                return Strategy(**strategy_doc)
        except Exception:
            pass
        
        # Fallback to default strategies
        strategy_doc = await self.db["default_strategies"].find_one({"_id": ObjectId(strategy_id)})
        if strategy_doc:
            return Strategy(**strategy_doc)
        return None

    async def _get_user_credentials(self, user_id: str) -> Optional[UserConfigInDB]:
        """Fetch user's encrypted API credentials from DB"""
        user_config_doc = await self.db["user_configs"].find_one({"user_id": user_id})
        if not user_config_doc:
            return None
        user_config = UserConfigInDB.from_mongo(user_config_doc)
        logger.debug(f"Fetched user config for user_id: {user_id}")
        return user_config

    async def _create_backtest_record(
        self,
        user_id: str,
        strategy_id: str,
        initial_capital: float,
        start_date: str,
        end_date: str,
        data_provider: str,
        timeframe: str
    ) -> ObjectId:
        """Create initial backtest record in database"""
        backtest_doc = {
            "_id": ObjectId(),
            "user_id": ObjectId(user_id),
            "strategy_id": ObjectId(strategy_id),
            "initial_capital": initial_capital,
            "start_date": start_date,
            "end_date": end_date,
            "data_provider": data_provider,
            "timeframe": timeframe,
            "status": BacktestStatus.PENDING.value,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
            "task_id": None,
            "result": None,
            "error": None
        }
        
        await self.db["backtests"].insert_one(backtest_doc)
        return backtest_doc["_id"]
    
    async def _update_backtest_task_id(self, backtest_id: ObjectId, task_id: str):
        """Update backtest record with Celery task ID"""
        await self.db["backtests"].update_one(
            {"_id": backtest_id},
            {"$set": {"task_id": task_id, "status": BacktestStatus.RUNNING.value}}
        )