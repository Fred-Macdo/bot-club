import logging
import polars as pl
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple
from bson import ObjectId

from ..indicators.indicator_factory import IndicatorFactory
from .portfolio_manager import Portfolio, Position
from .trade_logger import TradeLogger
from ..utils.condition_checker import ConditionChecker
from ..utils.indicator_converter import IndicatorConverter
from ..utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

class StrategyExecutor:
    """Handles strategy execution logic"""
    
    def __init__(self, db):
        self.db = db
        self.condition_checker = ConditionChecker()
        self.indicator_converter = IndicatorConverter()
        self.trade_logger = TradeLogger()
    
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
        
        # Check if DCA is enabled in strategy config
        dca_enabled = config.get('dollar_cost_averaging', {}).get('enabled', False)
        max_positions = config.get('dollar_cost_averaging', {}).get('max_positions', 1)
        
        logger.info(f"DCA enabled: {dca_enabled}, Max positions per symbol: {max_positions}")
        logger.info(f"Entry conditions: {entry_conditions}")
        logger.info(f"Exit conditions: {exit_conditions}")
        
        trades = []
        open_positions = {}  # Now stores lists of positions per symbol
        
        # Calculate indicators for each symbol
        symbol_data = self._calculate_indicators(data, config, symbols)
        
        # Process each symbol's data chronologically
        for symbol in symbols:
            if symbol not in symbol_data:
                logger.warning(f"No data available for symbol: {symbol}")
                continue
                
            symbol_df = symbol_data[symbol]
            logger.info(f"Processing {symbol} with {len(symbol_df)} rows")
            
            # Initialize positions list for this symbol
            if symbol not in open_positions:
                open_positions[symbol] = []
            
            # Use iter_rows(named=True) to iterate through the DataFrame efficiently
            for row_dict in symbol_df.iter_rows(named=True):
                
                logger.info(f"----------------------------------------")
                current_datetime = row_dict['datetime']
                current_price = row_dict['close']
                logger.info(f"Strategy Executor Current Date, Symbol, Price: {current_datetime}: {symbol} - {current_price}")
                
                # Create current prices dictionary for portfolio valuation
                current_prices = {symbol: current_price}
                
                # Check exit conditions for all open positions of this symbol
                positions_to_close = []
                for pos_idx, position in enumerate(open_positions[symbol]):
                    should_exit, exit_reason, exitdata_context = self.condition_checker.check_exit_conditions(
                        conditions=exit_conditions,
                        row=row_dict,
                        position=position,
                        current_time=row_dict['datetime']
                    )
                    
                    if should_exit:
                        logger.info(f"Exit Conditions: {exit_conditions}")
                        logger.info(f"Exit signal for {symbol} position {pos_idx}: {exit_reason}")
                        positions_to_close.append((pos_idx, position, exit_reason))
                
                # Close positions that meet exit conditions
                for pos_idx, position, exit_reason in reversed(positions_to_close):  # Reverse to maintain indices
                    close_position_row = {
                        'symbol': symbol,
                        'close': current_price,
                        'datetime': current_datetime
                    }
                    
                    trade = portfolio.close_position(position, close_position_row, current_datetime)
                    
                    if trade:
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
                            exit_reason=exit_reason
                        )
                        
                        trades.append(trade)
                    
                    # Remove the closed position
                    open_positions[symbol].pop(pos_idx)
                
                # Check entry conditions
                current_position_count = len(open_positions[symbol])
                can_add_position = (
                    dca_enabled and current_position_count < max_positions
                ) or (
                    not dca_enabled and current_position_count == 0
                )
                
                if can_add_position:
                    logger.info(f"Strategy Executor DEBUG: Entry Conditions: {entry_conditions}, Row: {row_dict}, Symbol: {symbol}, Symbol DF Shape: {symbol_df.shape}")
                    logger.info(f"Strategy Executor DEBUG: Current positions for {symbol}: {current_position_count}, Can add: {can_add_position}")
                    

                    should_enter, entry_reason, data_context = self.condition_checker.check_entry_conditions(
                        conditions=entry_conditions,
                        row=row_dict
                    )
                    
                    if should_enter:
                        logger.info(f"Entry signal for {symbol} (position #{current_position_count + 1}): {entry_reason}")
                        
                        open_position_row = {
                            'symbol': symbol,
                            'close': current_price,
                            'datetime': current_datetime
                        }
                        
                        position = portfolio.open_position(symbol, open_position_row, current_datetime, risk_mgmt)
                        
                        if position:
                            open_positions[symbol].append(position)
                                                        
                            # Log entry signal
                            self.trade_logger.log_entry_signal(
                                symbol,
                                current_datetime,
                                current_price,
                                strategy_name,
                                conditions_met=[entry_reason]
                            )
                
                # Update equity history for this row (regular update without action)
                portfolio.update_equity_history(current_datetime, current_prices)
        
        # Close remaining positions at the end
        total_remaining_positions = sum(len(positions) for positions in open_positions.values())
        if total_remaining_positions > 0:
            logger.info(f"Closing {total_remaining_positions} remaining positions")
            
            for symbol, positions in open_positions.items():
                if symbol in symbol_data and positions:
                    # Get the last row for this symbol using iter_rows
                    symbol_df = symbol_data[symbol]
                    final_row_dict = None
                    
                    # Get the last row efficiently
                    for final_row_dict in symbol_df.tail(1).iter_rows(named=True):
                        pass  # final_row_dict will be the last (and only) row
                    
                    if final_row_dict:
                        final_datetime = final_row_dict.get('datetime')
                        final_price = final_row_dict.get('close', 0)
                        
                        # Close all remaining positions for this symbol
                        for position in positions:
                            mock_row = {
                                'symbol': symbol,
                                'close': final_price,
                                'datetime': final_datetime
                            }
                            
                            trade = portfolio.close_position(position, mock_row, final_datetime)
                            
                            if trade:
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