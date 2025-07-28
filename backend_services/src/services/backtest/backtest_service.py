from datetime import datetime, date, timedelta
from typing import List, Any, Dict, Optional, Union
from pydantic import BaseModel, Field
from bson import ObjectId
import uuid
from fastapi import BackgroundTasks, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
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
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the BacktestService with a MongoDB database instance.
        Args:
            db (AsyncIOMotorDatabase): MongoDB database instance
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

    async def get_backtest_status(self, backtest_id: str):
        """Get the status of a backtest"""
        backtest = await self.db['backtest_executions'].find_one({'_id': ObjectId(backtest_id)})
        if not backtest:
            return None
        return {
            "status": backtest.get("status", "unknown"),
            "progress": backtest.get("progress", 0),
            "error": backtest.get("error")
        }

    async def start_backtest(self, strategy_id: str, user_id: str, params: dict):
        """Start a new backtest execution"""
        # Generate a proper ObjectId instead of UUID
        backtest_id = ObjectId()
        logger.info(f"Backtest_Service:Backtest ID: {backtest_id}")
        
        # Create backtest execution record
        execution_data = {
            "_id": backtest_id,
            "strategy_id": strategy_id,
            "user_id": user_id,
            "status": "running",
            "progress": 0,
            "params": params,
            "created_at": datetime.utcnow()
        }
        
        await self.db['backtest_executions'].insert_one(execution_data)
        
        # Start the backtest in background
        asyncio.create_task(self._execute_backtest(str(backtest_id), params))
        
        return str(backtest_id)

    async def _execute_backtest(self, backtest_id: str, params: dict):
        """Execute the backtest in background"""
        try:
            # Update status to running
            await self.db['backtest_executions'].update_one(
                {"_id": ObjectId(backtest_id)},
                {"$set": {"status": "running", "progress": 10}}
            )
            logger.info(f"Backtest_Service: Backtest ID: {backtest_id}")
            logger.info(f"Backtest_Service: Params: {params}")
            logger.info(f"Backtest_Service: Strategy ID: {params['strategy_id']}")
            logger.info(f"Backtest_Service: User ID: {params['user_id']}")
            logger.info(f"Backtest_Service: Initial Capital: {params['initial_capital']}")
            logger.info(f"Backtest_Service: Timeframe: {params['timeframe']}")
            logger.info(f"Backtest_Service: Start Date: {params['start_date']}")
            logger.info(f"Backtest_Service: End Date: {params['end_date']}")
            logger.info(f"Backtest_Service: Data Provider: {params['data_provider']}")
            logger.info(f"Starting Backtest from backtest_service to backtest_engine now")
            # Convert params to BacktestParams
            
            backtest_params = BacktestParams(
                strategy_id=params['strategy_id'],
                user_id=params['user_id'],
                initial_capital=params['initial_capital'],
                timeframe=params['timeframe'],
                start_date=datetime.strptime(params['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(params['end_date'], '%Y-%m-%d').date(),
                data_provider=params['data_provider']
            )
            
            # Run the backtest using the engine
            result = await self.backtest_engine.run(backtest_params)
 
            # Save results
            await self.db['backtests'].insert_one(result.model_dump())
            
            # Update execution status
            await self.db['backtest_executions'].update_one(
                {"_id": ObjectId(backtest_id)},
                {"$set": {"status": "completed", "progress": 100, "result_id": str(result.id)}}
            )
            
        except Exception as e:
            logger.error(f"Backtest execution failed: {e}", exc_info=True)
            await self.db['backtest_executions'].update_one(
                {"_id": ObjectId(backtest_id)},
                {"$set": {"status": "failed", "error": str(e)}}
            )

    async def cancel_backtest(self, backtest_id: str):
        """Cancel a running backtest"""
        result = await self.db['backtest_executions'].update_one(
            {"_id": ObjectId(backtest_id), "status": "running"},
            {"$set": {"status": "cancelled"}}
        )
        return result.modified_count > 0

    async def shutdown(self):
        """Shutdown the service"""
        logger.info("Shutting down backtest service")
