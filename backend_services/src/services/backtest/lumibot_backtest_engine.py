import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
import yaml
import tempfile
import os
import pandas as pd

from models.backtest import BacktestParams, BacktestResult

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading execution modes"""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class LumibotBacktestEngine:
    """
    Advanced backtesting engine that uses Lumibot for sophisticated backtesting
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, **kwargs):
        self.db = db
        self.active_trades = {}
        
    async def run_trading(
        self, 
        strategy_id: str, 
        mode: TradingMode,
        user_id: str,
        alpaca_config: Optional[Dict[str, Any]] = None,
        backtest_params: Optional[BacktestParams] = None,
        sleep_time: Optional[int] = 10
    ) -> Union[BacktestResult, Dict[str, Any]]:
        """
        Unified method to run trading in any mode using Lumibot
        
        Args:
            strategy_id: Strategy ID to execute
            mode: Trading mode (backtest, paper, live)
            user_id: User ID for authentication
            alpaca_config: Alpaca API configuration for live/paper trading
            backtest_params: Backtest parameters (only for backtest mode)
            
        Returns:
            BacktestResult for backtest mode, status dict for live/paper mode
        """
        logger.info(f"Starting {mode.value} trading for strategy: {strategy_id}")
        
        # Get strategy from database
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if mode == TradingMode.BACKTEST:
            if not backtest_params:
                raise ValueError("Backtest parameters required for backtest mode")
            return await self._run_lumibot_backtest(strategy, backtest_params)
        
        elif mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            return await self._run_lumibot_live_trading(strategy, mode, user_id, alpaca_config)
        
        else:
            raise ValueError(f"Invalid trading mode: {mode}")

    async def _run_lumibot_backtest(self, strategy: Dict[str, Any], params: BacktestParams) -> BacktestResult:
        """Execute backtest using Lumibot's sophisticated backtesting engine"""
        logger.info(f"Running Lumibot backtest for strategy: {strategy.get('name')}")
        
        # Get strategy configuration
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
        
        # Create a temporary YAML file for Lumibot
        yaml_config = self._create_lumibot_yaml_config(strategy, params)
        
        try:
            # Run Lumibot backtest using the command line interface
            result = await self._run_lumibot_backtest_cli(yaml_config, params)
            
            logger.info(f"Lumibot backtest completed: {result.total_trades} trades, {result.total_return:.2%} return")
            return result
            
        except Exception as e:
            logger.error(f"Error in Lumibot backtest: {e}")
            raise
        finally:
            # Clean up temporary file
            if os.path.exists(yaml_config):
                os.remove(yaml_config)

    async def _run_lumibot_backtest_cli(self, yaml_config: str, params: BacktestParams) -> BacktestResult:
        """Run Lumibot backtest using command line interface"""
        import subprocess
        import json
        
        # Create a temporary API keys file (dummy for backtesting)
        api_keys_file = self._create_dummy_api_keys()
        
        try:
            # Run Lumibot backtest command
            cmd = [
                'python', '-m', 'lumibot.backtesting',
                '--config', yaml_config,
                '--api-keys', api_keys_file,
                '--mode', 'backtest',
                '--start-date', params.start_date.strftime('%Y-%m-%d'),
                '--end-date', params.end_date.strftime('%Y-%m-%d'),
                '--initial-cash', str(params.initial_capital)
            ]
            
            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(yaml_config)
            )
            
            if result.returncode != 0:
                logger.error(f"Lumibot backtest failed: {result.stderr}")
                raise Exception(f"Lumibot backtest failed: {result.stderr}")
            
            # Parse the results (this would need to be adapted based on Lumibot's output format)
            # For now, return a basic result structure
            return self._parse_lumibot_output(result.stdout, params)
            
        finally:
            # Clean up temporary API keys file
            if os.path.exists(api_keys_file):
                os.remove(api_keys_file)

    def _create_dummy_api_keys(self) -> str:
        """Create a temporary API keys file for Lumibot"""
        api_keys = {
            'API_KEY': 'dummy_key',
            'API_SECRET': 'dummy_secret'
        }
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump(api_keys, temp_file, default_flow_style=False)
        temp_file.close()
        
        return temp_file.name

    def _parse_lumibot_output(self, output: str, params: BacktestParams) -> BacktestResult:
        """Parse Lumibot backtest output and convert to BacktestResult"""
        # This is a placeholder - you would need to adapt this based on Lumibot's actual output format
        # For now, return a basic result structure
        
        # Try to extract metrics from the output
        lines = output.split('\n')
        total_return = 0.0
        total_trades = 0
        win_rate = 0.0
        sharpe_ratio = 0.0
        max_drawdown = 0.0
        
        for line in lines:
            if 'Total Return' in line:
                try:
                    total_return = float(line.split(':')[-1].strip().replace('%', '')) / 100
                except:
                    pass
            elif 'Total Trades' in line:
                try:
                    total_trades = int(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Win Rate' in line:
                try:
                    win_rate = float(line.split(':')[-1].strip().replace('%', '')) / 100
                except:
                    pass
            elif 'Sharpe Ratio' in line:
                try:
                    sharpe_ratio = float(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Max Drawdown' in line:
                try:
                    max_drawdown = float(line.split(':')[-1].strip().replace('%', '')) / 100
                except:
                    pass
        
        return BacktestResult(
            strategy_id=params.strategy_id,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            total_trades=total_trades,
            profit_factor=0.0,  # Would need to extract from Lumibot output
            initial_capital=params.initial_capital,
            final_capital=params.initial_capital * (1 + total_return),
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
            timeframe=params.timeframe,
            trades=[],  # Would need to extract from Lumibot output
            equity_curve=[]  # Would need to extract from Lumibot output
        )

    def _create_lumibot_yaml_config(self, strategy: Dict[str, Any], params: BacktestParams) -> str:
        """Create a temporary YAML configuration file for Lumibot"""
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        
        # Create YAML content
        yaml_content = {
            'name': strategy.get('name', 'Lumibot Strategy'),
            'description': strategy.get('description', ''),
            'symbols': config.get('symbols', []),
            'timeframe': params.timeframe or config.get('timeframe', '1d'),
            'start_date': params.start_date.strftime('%Y-%m-%d'),
            'end_date': params.end_date.strftime('%Y-%m-%d'),
            'entry_conditions': config.get('entry_conditions', []),
            'exit_conditions': config.get('exit_conditions', []),
            'risk_management': config.get('risk_management', {}),
            'indicators': config.get('indicators', [])
        }
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump(yaml_content, temp_file, default_flow_style=False)
        temp_file.close()
        
        return temp_file.name

    async def _get_strategy_from_db(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get strategy from database as dictionary"""
        strategy_doc = await self.db['default_strategies'].find_one({'_id': ObjectId(strategy_id)})
        logger.info(f"Strategy retrieved from default_strategies: {strategy_doc}")  
        if strategy_doc is None:
            strategy_doc = await self.db['strategy'].find_one({'_id': ObjectId(strategy_id)})
            logger.info(f"Strategy retrieved from user strategies: {strategy_doc}")

        if strategy_doc is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if strategy_doc:
            logger.info(f"Strategy document retrieved from database: {strategy_doc}")
            logger.info(f"Strategy TYPE: {type(strategy_doc)}") 
            return strategy_doc
        
        return None

    async def _run_lumibot_live_trading(self, strategy: Dict[str, Any], mode: TradingMode, user_id: str, alpaca_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute live or paper trading using Lumibot"""
        logger.info(f"Starting Lumibot {mode.value} trading for strategy: {strategy.get('name')}")
        
        # This would integrate with Lumibot's live trading capabilities
        # For now, return a placeholder
        return {
            'status': 'not_implemented',
            'message': 'Live trading with Lumibot not yet implemented'
        } 