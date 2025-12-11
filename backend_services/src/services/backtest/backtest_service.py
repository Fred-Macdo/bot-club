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
        # Use mode='json' to convert date objects to strings for MongoDB
        backtest_data = backtest_params.model_dump(mode='json')
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
    
    async def run_backtest(self, strategy_id: str, user_id: str, params: Dict[str, Any]):
        """
        Run a backtest in the background using asyncio.create_task.
        Compatible with both aiohttp and FastAPI contexts.
        """
        # Convert params to BacktestParams
        params['strategy_id'] = strategy_id
        params['user_id'] = user_id
        
        try:
            backtest_params = BacktestParams(**params)
        except Exception as e:
            logger.error(f"Invalid backtest params: {e}")
            raise
            
        # Create record
        backtest_id = await self.create_backtest(backtest_params)
        
        # Define wrapper to run engine and save result
        async def run_and_save():
            try:
                await self.update_backtest_status(str(backtest_id), "running")
                
                # Run the backtest and get the result
                result = await self.backtest_engine.run(params=backtest_params)
                
                # Convert result to dictionary
                result_dict = result.model_dump(mode='json', exclude={'id'})
                
                # Update the DB record with the result metrics
                update_data = {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    **result_dict
                }
                
                await self.db['backtests'].update_one(
                    {"_id": backtest_id},
                    {"$set": update_data}
                )
                logger.info(f"Backtest {backtest_id} completed and results saved.")
                
            except Exception as e:
                logger.error(f"Backtest {backtest_id} failed: {e}", exc_info=True)
                await self.update_backtest_status(str(backtest_id), "failed", {"error": str(e)})

        # Start task using asyncio (works in both aiohttp and FastAPI)
        asyncio.create_task(run_and_save())
        
        return str(backtest_id)

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
