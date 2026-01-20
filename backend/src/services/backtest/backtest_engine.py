import asyncio
import logging
import polars as pl
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union, Literal
import yfinance as yf
from bson import ObjectId
from pymongo.database import Database
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy as LumiStrategy

from models.backtest import BacktestParams, BacktestResult
from models.user_config import ConfigEncryption
from models.strategy import StrategyConfig
from services.trading.crypto_strategy import CryptoStrategy
from services.trading.stock_strategy import StockStrategy
from ..data_retrieval.data_manager import DataManager
from ..utils.strategy_executor import StrategyExecutor
from ..utils.performance_calculator import PerformanceCalculator
from ..utils.trade_logger import TradeLogger
from ..utils.portfolio_manager import Portfolio
from ..utils.enums import TradingMode

logger = logging.getLogger(__name__)

class BacktestEngine:
    """Main backtesting engine orchestrator"""
    
    def __init__(self, db: Database):
        self.db = db
        self.data_manager = DataManager(db)
    
    async def run(self, params: BacktestParams) -> BacktestResult:
        """Execute a backtest."""

        logger.info(f"Backtest Engine DEBUG: Backtest Params: {params}")
        try:
            strategy_id_obj = ObjectId(params.strategy_id)
        except Exception:
            raise ValueError(f"Invalid strategy ID format: {params.strategy_id}")

        strategy = await self.db['default_strategies'].find_one({"_id": strategy_id_obj})
        if not strategy:
            strategy = await self.db['strategy'].find_one({"_id": strategy_id_obj})

        if not strategy:
            raise ValueError(f"Strategy {params.strategy_id} not found")

        logger.info(f"Backtest Engine DEBUG: Strategy found: {strategy.get('_id')}")
        user_id = params.user_id
        logger.info(f"Running backtest for strategy: {params.strategy_id}")
        
        strategy_executor = StrategyExecutor(db=self.db, user_id=params.user_id)
        performance_calculator = PerformanceCalculator()

        await self.data_manager.initialize_provider(params.data_provider, user_id)
        
        config = strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
        
        symbols = config.get('symbols', [])
        timeframe = params.timeframe or config.get('timeframe')
        
        data = await self.data_manager.fetch_historical_data(
            symbols, 
            params.start_date, 
            params.end_date, 
            params.timeframe
        )
        
        # FIX: Set cash equal to initial_capital
        portfolio = Portfolio(
            initial_capital=params.initial_capital, 
            cash=params.initial_capital
        )
        
        await strategy_executor.execute_strategy(strategy, data, portfolio)

        trades = strategy_executor.trade_logger.get_trades()

        strategy_executor.trade_logger.print_trade_summary()
        
        backtest_result = performance_calculator.create_backtest_result(
            strategy_id=params.strategy_id,
            user_id=user_id,
            trades=trades,
            initial_capital=params.initial_capital,
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
            timeframe=params.timeframe,
            equity_curve=portfolio.get_equity_curve()
        )
        
        strategy_executor.trade_logger.clear_trades()
        
        return backtest_result
    
    def shutdown(self):
        """Clean up resources if needed."""
        pass
