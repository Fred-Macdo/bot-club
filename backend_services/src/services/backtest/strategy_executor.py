import logging
import polars as pl
from datetime import datetime
from typing import Dict, Any, List
from bson import ObjectId

from ..indicators.indicator_factory import IndicatorFactory
from .portfolio_manager import Portfolio, Position
from .trade_logger import TradeLogger
from .utils.condition_checker import ConditionChecker
from .utils.indicator_converter import IndicatorConverter
from .utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

class StrategyExecutor:
    """Handles strategy execution logic"""
    
    def __init__(self, db):
        self.db = db
        self.condition_checker = ConditionChecker()
        self.indicator_converter = IndicatorConverter()
        self.trade_logger = TradeLogger()  # Add TradeLogger
    
    async def execute_strategy(self, strategy: Dict[str, Any], data: pl.DataFrame, portfolio: Portfolio) -> List['Trade']:
        """Execute the YAML-based trading strategy"""
        logger.info(f"Starting strategy execution with {len(data)} data points")
        
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
        
        symbols = config.get('symbols', [])
        entry_conditions = config.get('entry_conditions', [])
        exit_conditions = config.get('exit_conditions', [])
        risk_mgmt = config.get('risk_management', {})
        strategy_name = strategy.get('name', 'Unknown Strategy')
        
        trades = []
        open_positions = {}
        
        # Calculate indicators for each symbol
        symbol_data = self._calculate_indicators(data, config, symbols)
        
        # Process data chronologically
        unique_dates = data.select("datetime").unique().sort("datetime")
        
        for date_row in unique_dates.iter_rows(named=True):
            current_datetime = date_row['datetime']
            current_data = data.filter(pl.col("datetime") == current_datetime)
            
            for row in current_data.iter_rows(named=True):
                current_symbol = row.get('symbol')
                current_price = row.get('close', 0)
                
                if current_symbol not in symbol_data:
                    continue
                
                symbol_indicators = symbol_data[current_symbol]
                current_row_idx = symbol_indicators.filter(pl.col("datetime") == current_datetime)
                
                if len(current_row_idx) == 0:
                    continue
                
                current_row = current_row_idx.to_dicts()[0]
                
                # Check exit conditions first
                if current_symbol in open_positions:
                    position = open_positions[current_symbol]
                    if self.condition_checker.check_exit_conditions(exit_conditions, current_row, current_symbol, position, current_datetime):
                        trade = portfolio.close_position(position, row, current_datetime)
                        
                        # Log the trade to TradeLogger
                        self.trade_logger.log_trade(
                            symbol=trade.symbol,
                            entry_time=trade.entry_time,
                            exit_time=trade.exit_time,
                            entry_price=trade.entry_price,
                            exit_price=trade.exit_price,
                            quantity=trade.shares,
                            pnl=trade.pnl,
                            trade_type=trade.trade_type,
                            strategy_name=strategy_name,
                            exit_reason="exit_condition_met"
                        )
                        
                        trades.append(trade)
                        del open_positions[current_symbol]
                
                # Check entry conditions
                if current_symbol not in open_positions:
                    if self.condition_checker.check_entry_conditions(entry_conditions, current_row, current_symbol):
                        position = portfolio.open_position(current_symbol, row, current_datetime, risk_mgmt)
                        if position:
                            open_positions[current_symbol] = position
                            
                            # Log entry signal
                            self.trade_logger.log_entry_signal(
                                symbol=current_symbol,
                                timestamp=current_datetime,
                                price=current_price,
                                strategy_name=strategy_name
                            )
        
        # Close remaining positions
        final_datetime = unique_dates.tail(1).to_dicts()[0]['datetime']
        for symbol, position in open_positions.items():
            symbol_final_data = data.filter(
                (pl.col("datetime") == final_datetime) & (pl.col("symbol") == symbol)
            )
            
            if len(symbol_final_data) > 0:
                final_row = symbol_final_data.to_dicts()[0]
                trade = portfolio.close_position(position, final_row, final_datetime)
                
                # Log the final trade
                self.trade_logger.log_trade(
                    symbol=trade.symbol,
                    entry_time=trade.entry_time,
                    exit_time=trade.exit_time,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    quantity=trade.shares,
                    pnl=trade.pnl,
                    trade_type=trade.trade_type,
                    strategy_name=strategy_name,
                    exit_reason="end_of_period"
                )
                
                trades.append(trade)
        
        logger.info(f"Strategy execution completed. Total trades: {len(trades)}")
        return trades
    
    def _calculate_indicators(self, data: pl.DataFrame, config: Dict, symbols: List[str]) -> Dict[str, pl.DataFrame]:
        """Calculate indicators for each symbol"""
        symbol_data = {}
        for symbol in symbols:
            symbol_df = data.filter(pl.col("symbol") == symbol)
            if len(symbol_df) > 0:
                indicator_params = self.indicator_converter.convert_indicators_to_params(config.get('indicators', []))
                indicator_factory = IndicatorFactory(symbol_df, indicator_params)
                symbol_data[symbol] = indicator_factory.get_indicators()
                
                if symbol_data[symbol] is not None and len(symbol_data[symbol]) > 0:
                    logger.info(f"Indicator columns for {symbol}: {symbol_data[symbol].columns}")
        
        return symbol_data 