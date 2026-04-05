import logging
import polars as pl
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple
from decimal import Decimal
from bson import ObjectId

from ..services.data_retrieval.data_manager import DataManager

from .indicator_factory import IndicatorFactory
from ..models.portfolio_models import StrategyPortfolio, CompletedTrade, PositionLot
from .trade_logger import TradeLogger
from .condition_checker import ConditionChecker
from .indicator_converter import convert_indicators_to_params
from .date_utils import DateUtils
from .enums import TradingMode

logger = logging.getLogger(__name__)

class StrategyExecutor:
    """
    Handles strategy execution logic
    """
    
    def __init__(self, strategy: Dict[str, Any], data: Optional[pl.DataFrame] = None, initial_capital: float = 10000.0, encrypted_keys: Optional[Dict[str, str]] = None, data_provider: str = "alpaca"):
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.encrypted_keys = encrypted_keys or {}
        self.data_provider = data_provider
        
        # Instantiate (not assign class)
        self.condition_checker = ConditionChecker()
        self.trade_logger = TradeLogger()
        
        # Initialize StrategyPortfolio
        self.portfolio = StrategyPortfolio(
            strategy_id=ObjectId(strategy.get('_id', str(ObjectId()))),
            user_id=ObjectId(strategy.get('user_id', str(ObjectId()))),
            strategy_name=strategy.get('name', 'Backtest Strategy'),
            initial_capital=initial_capital,
            performance={
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0,
                "total_pnl_pct": 0.0
            }
        )
    
    async def execute_strategy(self) -> StrategyPortfolio:
        """Execute the YAML-based trading strategy"""
        if self.data is None or self.data.height == 0:
            try:
                self.data = await self._get_data()
            except Exception as e:
                logger.error(f"Failed to fetch data: {e}")
                return self.portfolio

        logger.info(f"Starting strategy execution with {self.data.height} data points")
        
        config = self.strategy.get('config')
        if not config:
            config = self.strategy
        #else:
            #
            # raise ValueError("No strategy configuration found")
        
        config_symbols = config.get('symbols', [])
        entry_conditions = config.get('entry_conditions', [])
        exit_conditions = config.get('exit_conditions', [])
        risk_mgmt = config.get('risk_management', {})
        strategy_name = self.strategy.get('name', 'Unknown Strategy')
        
        dca_config = config.get('dollar_cost_averaging', config.get('dollar_cost_average', {}))
        dca_enabled = dca_config.get('enabled', False)
        max_positions = dca_config.get('max_positions', 1)
        
        logger.info(f"DCA enabled: {dca_enabled}, Max positions per symbol: {max_positions}")
        
        # Calculate indicators for each symbol (includes _prev columns)
        symbol_data = self._calculate_indicators()
        logger.info(f"Calculated indicators for symbols: {list(symbol_data.keys())}")
        
        # Resolve which symbols to trade: use data symbols, filtered by config if possible
        available_symbols = list(symbol_data.keys())
        if config_symbols:
            symbols = [s for s in config_symbols if s in available_symbols]
            if not symbols:
                logger.warning(
                    f"Config symbols {config_symbols} not found in data {available_symbols}. "
                    f"Using all available data symbols."
                )
                symbols = available_symbols
        else:
            symbols = available_symbols
        
        logger.info(f"Trading symbols: {symbols}")
        
        # Process each symbol's data
        for symbol in symbols:
            symbol_df = symbol_data[symbol]
            logger.info(f"Processing {symbol} ({symbol_df.height} rows)...")

            for row_dict in symbol_df.iter_rows(named=True):
                current_datetime = row_dict['datetime']
                current_price = row_dict['close']
                current_price_dec = Decimal(str(current_price))
                
                current_prices = {symbol: current_price_dec}
                
                # --- RETRIEVE CURRENT LOTS FROM PORTFOLIO ---
                current_lots = self.portfolio.lots.get(symbol, [])
                
                # --- CHECK EXITS ---
                lots_to_close = []
                
                if current_lots:
                    # check_exit_conditions returns (bool, conditions_met, row) or (False, None, None)
                    should_exit, exit_details, _ = self.condition_checker.check_exit_conditions(
                        conditions=exit_conditions,
                        row=row_dict
                    )
                    
                    if should_exit:
                        # Build a reason string from the exit conditions that fired
                        exit_reason = "Strategy Exit"
                        if exit_details:
                            fired = [exit_conditions[i].get('indicator', 'unknown') 
                                     for i, met in enumerate(exit_details) if met]
                            if fired:
                                exit_reason = f"Exit: {', '.join(fired)}"
                        
                        self.trade_logger.log_exit_signal(
                            symbol=symbol,
                            timestamp=current_datetime,
                            price=current_price,
                            reason=exit_reason,
                            strategy_name=strategy_name
                        )
                        
                        # Mark ALL lots for this symbol to close
                        for lot in current_lots:
                            lots_to_close.append((lot, exit_reason))
                
                # Perform Sells
                for lot, exit_reason in lots_to_close:
                    realized_trades = self.portfolio.process_sell(
                        symbol=symbol,
                        quantity=lot.quantity, 
                        exit_price=current_price_dec,
                        exit_time=current_datetime,
                        reason=exit_reason
                    )
                    
                    for trade in realized_trades:
                        self.trade_logger.log_trade(
                            symbol=trade.symbol,
                            entry_time=trade.entry_time,
                            exit_time=trade.exit_time,
                            entry_price=float(trade.entry_price),
                            exit_price=float(trade.exit_price),
                            quantity=float(trade.quantity), 
                            pnl=float(trade.realized_pnl),    
                            trade_type=trade.trade_type,
                            strategy_name=strategy_name,
                            entry_reason=trade.entry_reason,
                            exit_reason=trade.exit_reason
                        )
                
                # Refresh lots after exits
                current_lots = self.portfolio.lots.get(symbol, [])
                current_position_count = len(current_lots)
                
                # --- CHECK ENTRIES ---
                can_add_position = (
                    (dca_enabled and current_position_count < max_positions) or 
                    (not dca_enabled and current_position_count == 0)
                )
                
                if can_add_position:
                    # check_entry_conditions returns (bool, row) or (False, None)
                    should_enter, _ = self.condition_checker.check_entry_conditions(
                        conditions=entry_conditions,
                        row=row_dict
                    )
                    
                    if should_enter:
                        self.trade_logger.log_entry_signal(
                            symbol=symbol,
                            timestamp=current_datetime,
                            price=current_price,
                            strategy_name=strategy_name
                        )

                        allocation_pct = risk_mgmt.get('position_size_pct', risk_mgmt.get('risk_per_trade', 0.1))
                        if allocation_pct > 1: 
                            allocation_pct /= 100
                        allocation_pct_dec = Decimal(str(allocation_pct))
                        
                        amount_to_invest = self.portfolio.current_cash * allocation_pct_dec
                        
                        # Cap at available cash
                        if amount_to_invest > self.portfolio.current_cash:
                             amount_to_invest = self.portfolio.current_cash
                        
                        if amount_to_invest >= current_price_dec * Decimal("0.0001"):
                            quantity = amount_to_invest / current_price_dec
                            
                            new_lot = PositionLot(
                                symbol=symbol,
                                quantity=quantity,
                                entry_price=current_price_dec,
                                entry_time=current_datetime,
                                cost_basis=quantity * current_price_dec,
                                strategy_id=str(self.portfolio.strategy_id),
                                user_id=str(self.portfolio.user_id),
                                entry_reason="Entry Signal"
                            )
                            
                            self.portfolio.add_buy(new_lot)
                            self.portfolio.current_cash -= new_lot.cost_basis

                # --- UPDATE EQUITY CURVE ---
                self.portfolio.update_equity_curve(current_prices)

        # --- END OF SIMULATION: CLOSE ALL ---
        logger.info("End of simulation. Closing remaining positions...")
        
        active_symbols = list(self.portfolio.lots.keys())
        
        for symbol in active_symbols:
            positions = self.portfolio.lots.get(symbol, [])
            if symbol in symbol_data and positions:
                last_row = symbol_data[symbol].tail(1).to_dicts()
                if not last_row: 
                    continue
                
                final_price = Decimal(str(last_row[0]['close']))
                final_time = last_row[0]['datetime']
                
                total_qty = self.portfolio.get_position_quantity(symbol)
                
                realized_trades = self.portfolio.process_sell(
                    symbol=symbol,
                    quantity=total_qty,
                    exit_price=final_price,
                    exit_time=final_time,
                    reason="Backtest End"
                )

                for trade in realized_trades:
                     self.trade_logger.log_trade(
                        symbol=trade.symbol,
                        entry_time=trade.entry_time,
                        exit_time=trade.exit_time,
                        entry_price=float(trade.entry_price),
                        exit_price=float(trade.exit_price),
                        quantity=float(trade.quantity), 
                        pnl=float(trade.realized_pnl),    
                        trade_type=trade.trade_type,
                        strategy_name=strategy_name,
                        entry_reason=trade.entry_reason,
                        exit_reason=trade.exit_reason
                    )

        # --- UPDATE METRICS ---
        self.portfolio.update_performance_metrics()
        self.trade_logger.print_trade_summary()
        
        return self.portfolio
    
    def _calculate_indicators(self) -> Dict[str, pl.DataFrame]:
        """Calculate indicators per symbol and add _prev columns for crossover detection"""
        symbol_data = {}
        if self.data is None or self.data.height == 0: 
            return {}
        
        config = self.strategy.get('config')
        if not config:
            config = self.strategy
        
        data_clean = self.data.rename({col: col.lower() for col in self.data.columns})
        if 'symbol' not in data_clean.columns:
            logger.error("Data missing 'symbol' column")
            return {}

        symbols = data_clean['symbol'].unique().to_list()
        
        for symbol in symbols:
            symbol_df = data_clean.filter(pl.col("symbol") == symbol).sort('datetime')
            if symbol_df.height > 0:
                indicator_params = convert_indicators_to_params(indicators=config.get('indicators', []))
                indicator_factory = IndicatorFactory(symbol_df, indicator_params)
                result_df = indicator_factory.get_indicators()
                
                # Add _prev columns for ALL numeric columns (indicators + OHLCV)
                # This supports crossovers like "close crosses_above open"
                skip_cols = {'datetime', 'symbol', 'date'}
                for col in result_df.columns:
                    col_lower = col.lower()
                    if col_lower not in skip_cols and not col_lower.endswith('_prev'):
                        result_df = result_df.with_columns(
                            pl.col(col).shift(1).alias(f'{col}_prev')
                        )
                
                symbol_data[symbol] = result_df
        
        return symbol_data

    async def _get_data(self) -> pl.DataFrame:
        """Fetch historical data for the strategy"""
        if self.data is None or self.data.height == 0:
            data_manager = DataManager(keys=self.encrypted_keys, provider_name=self.data_provider)
            config = self.strategy.get('config')
            if not config:
                config = self.strategy
            self.data = await data_manager.fetch_historical_data(
                symbols=config.get('symbols', []),
                start_date=config.get('start_date'),
                end_date=config.get('end_date'),
                timeframe=config.get('timeframe', '1d')
            )
        return self.data
