import asyncio
import logging
import polars as pl
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union, Literal
import yfinance as yf
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.backtest import BacktestParams, BacktestResult
from models.user_config import ConfigEncryption
from ..data_retrieval.data_manager import DataManager
from ..trading.strategy_executor import StrategyExecutor
from ..trading.performance_calculator import PerformanceCalculator
from ..trading.trade_logger import TradeLogger
from ..trading.live_trading import LiveTradingManager
from ..trading.portfolio_manager import Portfolio, Position, Trade
from ..utils.enums import TradingMode

logger = logging.getLogger(__name__)

class BacktestEngine:
    """Main backtesting engine orchestrator"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.data_manager = DataManager(db)
        self.strategy_executor = StrategyExecutor(db)
        self.performance_calculator = PerformanceCalculator()
        self.trade_logger = TradeLogger()
        self.live_trading = LiveTradingManager(db)
    
    async def run_trading(self, strategy_id: str, mode: TradingMode, user_id: str, 
                         alpaca_config: Optional[Dict[str, Any]] = None,
                         backtest_params: Optional[BacktestParams] = None) -> Union[BacktestResult, Dict[str, Any]]:
        """Main entry point for running trading strategies"""
        logger.info(f"Starting {mode.value} trading for strategy: {strategy_id}")
        
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if mode == TradingMode.BACKTEST:
            if not backtest_params:
                raise ValueError("Backtest parameters required for backtest mode")
            return await self._run_backtest(strategy, backtest_params, user_id)
        
        elif mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            return await self.live_trading.run_live_trading(strategy, mode, user_id, alpaca_config)
        
        else:
            raise ValueError(f"Invalid trading mode: {mode}")
    
    async def _run_backtest(self, strategy: Dict[str, Any], params: BacktestParams, user_id: str) -> BacktestResult:
        """Execute backtest mode"""
        logger.info(f"Running backtest for strategy: {strategy.get('name')}")
        
        # CLEAR TRADE LOGGERS BEFORE EACH BACKTEST RUN
        self.trade_logger.clear_trades()
        self.strategy_executor.trade_logger.clear_trades()
        
        # Initialize data provider using the data_provider from params
        await self.data_manager.initialize_provider(params.data_provider, user_id)
        
        # Get strategy configuration
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
        
        symbols = config.get('symbols', [])
        timeframe = params.timeframe or config.get('timeframe')
        
        # Fetch historical data
        data = await self.data_manager.fetch_historical_data(
            symbols, params.start_date, params.end_date, timeframe
        )
        
        # Initialize portfolio
        portfolio = Portfolio(initial_capital=params.initial_capital)
        
        # Execute strategy
        trade_objects = await self.strategy_executor.execute_strategy(strategy, data, portfolio)

        # Get trades from the TradeLogger (which now has all the logged trades)
        trades = self.strategy_executor.trade_logger.get_trades()

        # Log trade summary
        self.strategy_executor.trade_logger.print_trade_summary()
        
        # Create BacktestResult directly from PerformanceCalculator
        backtest_result = self.performance_calculator.create_backtest_result(
            strategy_id=params.strategy_id,
            user_id=user_id,
            trades=trades,  # Now passing dictionaries instead of Trade objects
            initial_capital=params.initial_capital,
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
            timeframe=params.timeframe,
            equity_curve=portfolio.get_equity_curve() if hasattr(portfolio, 'get_equity_curve') else None
        )
        
        # CLEAR TRADE LOGGERS AFTER BACKTEST COMPLETES (cleanup)
        self.trade_logger.clear_trades()
        self.strategy_executor.trade_logger.clear_trades()
        
        return backtest_result
    
    async def _get_strategy_from_db(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get strategy from database"""
        strategy_doc = await self.db['default_strategies'].find_one({'_id': ObjectId(strategy_id)})
        if strategy_doc is None:
            strategy_doc = await self.db['strategy'].find_one({'_id': ObjectId(strategy_id)})
        
        if strategy_doc is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        return strategy_doc
