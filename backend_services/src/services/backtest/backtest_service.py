from datetime import datetime, date, timedelta
from typing import List, Any, Dict, Optional, Union
from pydantic import BaseModel, Field
from bson import ObjectId
import uuid
from fastapi import BackgroundTasks, HTTPException
from pymongo.database import Database
import asyncio
import aiohttp
import logging

from models.strategy import Strategy
from models.backtest import BacktestParams, BacktestResult
from .backtest_engine import BacktestEngine
from ..utils.enums import TradingMode
from config import MONGO_DB, SERVICE_PORT, API_SERVICE_URL

logger = logging.getLogger(__name__)

class BacktestService:
    """
    This class is responsible for creating and retrieving backtests from the database.
    """
    def __init__(self, db: Database):
        """
        Initialize the BacktestService with a MongoDB database instance.
        Args:
            db (Database): MongoDB database instance
        """
        self.db = db
        self.backtest_engine = BacktestEngine(db=db)

    async def initialize(self):
        """Initialize the backtest service"""
        logger.info("Initializing backtest service")
        # Ensure we have the necessary collections
        collections = await self.db.list_collection_names()
        if "backtest_executions" not in collections:
            logger.info("Creating backtest_executions collection")
            await self.db.create_collection("backtest_executions")

    async def create_backtest(self, backtest_params: BacktestParams):
        """Create a new backtest"""
        backtest_data = backtest_params.model_dump()
        result = await self.db['backtests'].insert_one(backtest_data)
        logger.info(f"Backtest created with ID: {result.inserted_id}")

        return result.inserted_id

    async def get_backtest(self, backtest_id: str):
        """Get a backtest by its ID
        Args:
            backtest_id (str): The ID of the backtest to retrieve
        Returns:
            BacktestResult: The backtest result
        """
        backtest = await self.db['backtests'].find_one({'_id': ObjectId(backtest_id)})
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")
        return BacktestResult(**backtest)

    async def get_all_backtests(self, user_id: str):
        """Get all backtests for a user"""
        cursor = self.db['backtests'].find({"user_id": user_id})
        return await cursor.to_list(length=None)

    async def update_backtest_status(self, backtest_id: str, status: str, result: Optional[Dict] = None):
        """Update the status of a backtest"""
        update_data = {"status": status}
        if result:
            update_data["result"] = result
        
        await self.db['backtests'].update_one(
            {"_id": ObjectId(backtest_id)},
            {"$set": update_data}
        )
    
    async def run_backtest(self, backtest_params: BacktestParams, background_tasks: BackgroundTasks):
        """
        Run a backtest in the background.
        This method will save the backtest parameters to the database and then
        schedule the backtest to run in the background.
        """
        try:
            # 1. Create a backtest record in the database
            backtest_id = await self.create_backtest(backtest_params)
            
            # 2. Schedule the backtest to run in the background
            background_tasks.add_task(
                self.backtest_engine.run,
                backtest_id=str(backtest_id),
                params=backtest_params
            )
            
            return backtest_id
        except Exception as e:
            logger.error(f"Error starting backtest: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to start backtest")

    async def get_backtest_status(self, backtest_id: str):
        """Get the status of a backtest"""
        backtest = await self.get_backtest(backtest_id)
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")
        return {"status": backtest.get("status", "pending"), "result": backtest.get("result")}

    async def cancel_backtest(self, backtest_id: str):
        """Cancel a running backtest"""
        # This is a simplified implementation. A real implementation would need
        # to handle the aiohttp task cancellation properly.
        await self.update_backtest_status(backtest_id, "cancelled")
        return {"status": "cancelled"}
    
    async def shutdown(self):
        """Shutdown the backtest service"""
        await self.backtest_engine.shutdown()
        logger.info("Backtest service shut down")
