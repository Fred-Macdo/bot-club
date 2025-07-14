from datetime import datetime, date
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
from .enums import TradingMode
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
        logger.info(f"Creating backtest with data: {backtest_data}")
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
                initial_capital=params['initial_capital'],
                timeframe=params['timeframe'],
                start_date=datetime.strptime(params['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(params['end_date'], '%Y-%m-%d').date(),
                data_provider=params['data_provider']
            )
            
            # Run the backtest using the engine - FIXED: use run_trading instead of run_backtest
            result = await self.backtest_engine.run_trading(
                strategy_id=params['strategy_id'],
                mode=TradingMode.BACKTEST,
                user_id=params['user_id'],
                backtest_params=backtest_params
            )
            
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

    async def run_trading(
        self, 
        strategy_id: str, 
        mode: TradingMode,
        user_id: str,
        alpaca_config: Optional[Dict[str, Any]] = None,
        backtest_params: Optional[BacktestParams] = None
    ) -> Union[BacktestResult, Dict[str, Any]]:
        """
        Unified method to run trading in any mode
        
        Args:
            strategy_id: Backtest executionID to execute
            mode: Trading mode (backtest, paper, live)
            user_id: User ID for authentication
            alpaca_config: Alpaca API configuration for live/paper trading
            backtest_params: Backtest parameters (only for backtest mode)
            
        Returns:
            BacktestResult for backtest mode, status dict for live/paper mode
        """
        logger.info(f"Starting {mode.value} trading for strategy: {strategy_id}")
        
        # Get Backtest executionfrom database
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if mode == TradingMode.BACKTEST:
            if not backtest_params:
                raise ValueError("Backtest parameters required for backtest mode")
            return await self.backtest_engine.run_trading(
                strategy_id=strategy_id,
                mode=mode,
                user_id=user_id,
                backtest_params=backtest_params
            )
        
        elif mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            return await self.backtest_engine.run_trading(
                strategy_id=strategy_id,
                mode=mode,
                user_id=user_id,
                alpaca_config=alpaca_config
            )
        
        else:
            raise ValueError(f"Invalid trading mode: {mode}")

    async def stop_trading(self, strategy_id: str) -> Dict[str, Any]:
        """Stop live/paper trading for a strategy"""
        return await self.backtest_engine.stop_trading(strategy_id)

    async def get_trading_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get current trading status"""
        return await self.backtest_engine.get_trading_status(strategy_id)

    async def shutdown(self):
        """Shutdown the service"""
        logger.info("Shutting down backtest service")
