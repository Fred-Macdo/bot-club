import asyncio
import logging
import polars as pl
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Literal
import yfinance as yf
from enum import Enum
from bson import ObjectId
#from lumibot.strategies.strategy import Strategy
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.backtest import BacktestParams, BacktestResult
from ..indicators.indicator_factory import IndicatorFactory
from ..data_retrieval.alpaca_data_fetcher import AlpacaDataFetcher
from ..data_retrieval.data_providers import DataProviderFactory, BaseDataProvider


logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading execution modes"""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class BacktestEngine:
    """
    Core backtesting engine that executes YAML-based trading strategies
    Supports backtesting, paper trading, and live trading modes
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, data_provider_config: Optional[Dict[str, Any]] = None, **kwargs):
        self.db = db
        self.data_cache = {}  # Cache for historical data
        self.alpaca_clients = {}  # Cache for Alpaca clients
        self.active_trades = {}
        
        # Initialize data provider
        if data_provider_config:
            self.data_provider = DataProviderFactory.get_provider(**data_provider_config)
        else:
            # Default to Yahoo Finance provider
            self.data_provider = DataProviderFactory.get_provider('yahoo')
        
        # Trade logging
        self.trade_log = []
        self.trade_counter = 0

    def set_indicator_params(self, indicator_params: Dict[str, Any]):
        """
        Set the indicator parameters for the backtest engine
        Args:
            indicator_params: Dictionary of indicator parameters
        """
        self.indicator_params = indicator_params

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
        Unified method to run trading in any mode
        
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
        logger.info(f"Backtest_Engine: Backtest Params: {backtest_params}")
        logger.info(f"Backtest_Engine: Mode: {mode}")
        logger.info(f"Backtest_Engine: User ID: {user_id}")
        logger.info(f"Backtest_Engine: Alpaca Config: {alpaca_config}")
        logger.info(f"Backtest_Engine: Strategy ID: {strategy_id}")
        logger.info(f"Backtest_Engine: Starting Backtest from backtest_engine to backtest_service now")

        
        # Get strategy from database
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if mode == TradingMode.BACKTEST:
            if not backtest_params:
                raise ValueError("Backtest parameters required for backtest mode")
            return await self._run_backtest(strategy, backtest_params)
        
        elif mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            return await self._run_live_trading(strategy, mode, user_id, alpaca_config)
        
        else:
            raise ValueError(f"Invalid trading mode: {mode}")

    async def _run_backtest(self, strategy: Dict[str, Any], params: BacktestParams) -> BacktestResult:
        """Execute backtest mode"""
        logger.info(f"Running backtest for strategy: {strategy.get('name')}")
        logger.info(f"Strategy TYPE: {type(strategy)}")
        
        # Reset trade log for new backtest
        self.trade_log = []
        self.trade_counter = 0
        
        # Get strategy configuration - handle both yaml_config and strategy_config
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
            
        symbols = config.get('symbols', [])
        timeframe = params.timeframe or config.get('timeframe')
        
        # Get historical data
        data = await self._fetch_historical_data(
            symbols, 
            params.start_date, 
            params.end_date, 
            timeframe
        )
        
        # Initialize portfolio
        portfolio = Portfolio(initial_capital=params.initial_capital)
        
        # Execute strategy
        trades = await self._execute_yaml_strategy(strategy, data, portfolio)
        
        # Calculate performance metrics
        metrics = self._calculate_performance_metrics(
            portfolio, 
            trades, 
            params.initial_capital
        )
        
        # Print trade summary
        self.print_trade_summary()
        
        # Create result object
        result = BacktestResult(
            strategy_id=params.strategy_id,
            total_return=metrics['total_return'],
            sharpe_ratio=metrics['sharpe_ratio'],
            max_drawdown=metrics['max_drawdown'],
            win_rate=metrics['win_rate'],
            total_trades=len(trades),
            profit_factor=metrics['profit_factor'],
            initial_capital=params.initial_capital,
            final_capital=portfolio.total_value,
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
            timeframe=timeframe,
            trades=[trade.to_dict() for trade in trades],
            equity_curve=portfolio.get_equity_curve()
        )
        
        logger.info(f"Backtest completed: {len(trades)} trades, {metrics['total_return']:.2%} return")
        return result

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
        
        self.set_indicator_params(strategy_doc.config.get('indicators', []))
        logger.info(f"Backtest_Engine: Indicator Params: {self.indicator_params}") 
        
        return None
        
    async def _fetch_historical_data(
        self, 
        symbols: List[str], 
        start_date: str, 
        end_date: str, 
        timeframe: str
    ) -> pl.DataFrame:
        """Fetch historical price data for the given symbols as Polars DataFrame"""
        
        cache_key = f"{'-'.join(symbols)}_{start_date}_{end_date}_{timeframe}"
        
        if cache_key in self.data_cache:
            logger.info(f"Using cached data for {symbols}")
            return self.data_cache[cache_key]
            
        logger.info(f"Fetching data for {symbols} from {start_date} to {end_date}")
        
        try:
            # Convert timeframe to yfinance format
            interval_map = {
                '1d': '1d',
                '1h': '1h',
                '15m': '15m',
                '5m': '5m'
            }
            yf_interval = interval_map.get(timeframe, '1d')
            
            # Fetch data for each symbol
            all_data = []
            for symbol in symbols:
                ticker = yf.Ticker(symbol)
                data = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=yf_interval
                )
                
                if not data.empty:
                    # Convert to Polars DataFrame
                    pl_data = pl.from_pandas(data.reset_index())
                    # Add symbol column
                    pl_data = pl_data.with_columns(pl.lit(symbol).alias("symbol"))
                    all_data.append(pl_data)
                    
            if not all_data:
                raise ValueError("No data retrieved for any symbols")
                
            # Combine all symbol data using Polars concat
            combined_data = pl.concat(all_data, how="vertical")
            
            # Ensure consistent column names (yfinance uses different names)
            column_mapping = {
                'Date': 'datetime',
                'Datetime': 'datetime',
                'Open': 'open',
                'High': 'high', 
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            }
            
            # Rename columns if they exist
            existing_cols = combined_data.columns
            rename_dict = {col: column_mapping[col] for col in existing_cols if col in column_mapping}
            if rename_dict:
                combined_data = combined_data.rename(rename_dict)
            
            # FIXED: Sort by datetime first, then symbol for chronological processing
            combined_data = combined_data.sort(["datetime", "symbol"])
            
            # Cache the data
            self.data_cache[cache_key] = combined_data
            
            logger.info(f"Retrieved {len(combined_data)} data points")
            logger.info(f"Date range: {combined_data['datetime'].min()} to {combined_data['datetime'].max()}")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise

    async def _execute_yaml_strategy(
        self, 
        strategy: Dict[str, Any], 
        data: pl.DataFrame, 
        portfolio: 'Portfolio'
    ) -> List['Trade']:
        """Execute the YAML-based trading strategy against historical data using Polars"""
        logger.info(f"Starting strategy execution with {len(data)} data points")
        logger.info(f"Initial cash: ${portfolio.cash:.2f}")
        
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
            
        symbols = config.get('symbols', [])
        
        # Debug: Verify data structure
        self._debug_data_structure(data, symbols)
        
        entry_conditions = config.get('entry_conditions', [])
        exit_conditions = config.get('exit_conditions', [])
        risk_mgmt = config.get('risk_management', {})
        
        trades = []
        open_positions = {}
        
        # Calculate indicators for each symbol first
        symbol_data = {}
        for symbol in config.get('symbols', []):
            symbol_df = data.filter(pl.col("symbol") == symbol)
            if len(symbol_df) > 0:
                # Create indicator factory with strategy parameters
                indicator_params = self._convert_indicators_to_params(config.get('indicators', []))
                indicator_factory = IndicatorFactory(symbol_df, indicator_params)
                symbol_data[symbol] = indicator_factory.get_indicators()
                
                # Debug: Log the columns in the indicator data
                if symbol_data[symbol] is not None and len(symbol_data[symbol]) > 0:
                    logger.info(f"Indicator columns for {symbol}: {symbol_data[symbol].columns}")
        
        # FIXED: Process data chronologically by datetime, but ensure we get the correct price for each symbol
        # Get unique datetime values and sort them
        unique_dates = data.select("datetime").unique().sort("datetime")
        
        for date_row in unique_dates.iter_rows(named=True):
            current_datetime = date_row['datetime']
            
            # Get all symbols' data for this datetime
            current_data = data.filter(pl.col("datetime") == current_datetime)
            
            # Process each symbol for this datetime
            for row in current_data.iter_rows(named=True):
                current_symbol = row.get('symbol')
                current_price = row.get('close', 0)
                
                # Debug: Log the current symbol and price being processed
                logger.debug(f"Processing {current_symbol} at {current_datetime} with price ${current_price:.2f}")
                
                # Get indicator data for current symbol
                if current_symbol not in symbol_data:
                    continue
                    
                symbol_indicators = symbol_data[current_symbol]
                current_row_idx = symbol_indicators.filter(
                    pl.col("datetime") == current_datetime
                )
                
                if len(current_row_idx) == 0:
                    continue
                    
                current_row = current_row_idx.to_dicts()[0]  # Convert to dict for easier access
                
                # Check for exit conditions first - FIXED: Only check for the current symbol's position
                if current_symbol in open_positions:
                    position = open_positions[current_symbol]
                    if self._check_exit_conditions(exit_conditions, current_row, current_symbol, position, current_datetime):
                        # FIXED: Use the current symbol's price data for the exit
                        trade = self._close_position(portfolio, position, row, current_datetime)
                        trades.append(trade)
                        del open_positions[current_symbol]
                        
                # Check for entry conditions - FIXED: Only check for the current symbol
                if current_symbol not in open_positions:
                    if self._check_entry_conditions(entry_conditions, current_row, current_symbol):
                        position = self._open_position(
                            portfolio, 
                            current_symbol, 
                            row, 
                            current_datetime, 
                            risk_mgmt
                        )
                        if position:
                            open_positions[current_symbol] = position
                            
        # Close any remaining open positions at the end
        final_datetime = unique_dates.tail(1).to_dicts()[0]['datetime']
        
        for symbol, position in open_positions.items():
            # FIXED: Find the final row for this specific symbol
            symbol_final_data = data.filter(
                (pl.col("datetime") == final_datetime) & 
                (pl.col("symbol") == symbol)
            )
            
            if len(symbol_final_data) > 0:
                final_row = symbol_final_data.to_dicts()[0]
                trade = self._close_position(portfolio, position, final_row, final_datetime)
                trades.append(trade)
            else:
                # If no final data for this symbol, use the last available data
                symbol_data_filtered = data.filter(pl.col("symbol") == symbol).sort("datetime")
                if len(symbol_data_filtered) > 0:
                    final_row = symbol_data_filtered.tail(1).to_dicts()[0]
                    trade = self._close_position(portfolio, position, final_row, final_row['datetime'])
                    trades.append(trade)
        
        logger.info(f"Strategy execution completed. Total trades: {len(trades)}")
        logger.info(f"Final cash: ${portfolio.cash:.2f}")
        logger.info(f"Total portfolio value: ${portfolio.total_value:.2f}")
        
        return trades

    def _convert_indicators_to_params(self, indicators: List[Dict]) -> Dict:
        """Convert strategy indicators to IndicatorFactory parameters"""
        params = {}
        for indicator in indicators:
            name = indicator.get('name', '').lower()
            indicator_params = indicator.get('params', {})
            
            # Handle indicators that need period-based naming
            if name in ['sma', 'ema']:
                period = indicator_params.get('period', 20)
                key = f"{name}_{period}"
                params[key] = indicator_params
            elif name == 'rsi':
                params['rsi'] = indicator_params
            elif name == 'bollinger_bands':
                params['bollinger_bands'] = {
                    'period': indicator_params.get('period', 20),
                    'std_dev': indicator_params.get('std_dev', 2)
                }
            elif name == 'atr':
                params['atr'] = indicator_params
            elif name == 'adx':
                params['adx'] = indicator_params
            elif name == 'obv':
                params['obv'] = {}
            elif name == 'mfi':
                params['mfi'] = indicator_params
            elif name == 'cci':
                params['cci'] = indicator_params
            elif name == 'vwap':
                params['vwap'] = indicator_params
            else:
                # For any other indicators, use the name as is
                params[name] = indicator_params
        
        return params

    def _check_entry_conditions(
        self, 
        conditions: List[Dict], 
        row: Dict[str, Any], 
        symbol: str
    ) -> bool:
        """Check if entry conditions are met using YAMLStrategy logic"""
        if not conditions:
            return False
            
        return all(
            self._check_condition(row, condition)
            for condition in conditions
        )

    def _check_exit_conditions(
        self, 
        conditions: List[Dict], 
        row: Dict[str, Any], 
        symbol: str, 
        position: 'Position',
        current_time: datetime
    ) -> bool:
        """Check if exit conditions are met using YAMLStrategy logic"""
        if not conditions:
            # Default exit conditions
            current_price = row.get('close', position.entry_price)
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            
            # Exit after 10% profit/loss or 5 days
            if abs(pnl_pct) > 0.1 or position.get_days_held(current_time) > 5:
                return True
            return False
            
        return any(
            self._check_condition(row, condition)
            for condition in conditions
        )

    def _check_condition(self, row: Dict[str, Any], condition_config: Dict) -> bool:
        """
        Check entry/exit condition using YAMLStrategy logic
        """
        valid_comparisons = ['above', 'below', 'between', 'crosses_above', 'crosses_below', 'equals']
        comparison = condition_config.get('comparison')
        
        if comparison not in valid_comparisons:
            raise ValueError(f"Comparison '{comparison}' is not valid. Must be one of {valid_comparisons}")
        
        indicator = condition_config.get('indicator')
        value = condition_config.get('value')
        
        # Ensure indicator is lowercase for consistent access
        indicator_key = indicator.lower()
        
        # Handle special indicators with dedicated comparisons
        if indicator == "MACD" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_macd_cross(row, comparison)
        
        elif indicator == "BBANDS" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_bbands_cross(row, comparison, value)
        
        # Handle general comparison cases
        if comparison == "above":
            return self._check_above(row, indicator_key, value)
        
        elif comparison == "below":
            return self._check_below(row, indicator_key, value)
        
        elif comparison == "crosses_above":
            return self._check_crosses_above(row, indicator_key, value)
        
        elif comparison == "crosses_below":
            return self._check_crosses_below(row, indicator_key, value)
        
        elif comparison == "between":
            return self._check_between(row, indicator_key, value)
        
        elif comparison == "equals":
            if isinstance(value, str):
                return row[indicator_key] == row[value.lower()]
            else:
                return row[indicator_key] == value
            
        return False

    def _check_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator is above a value or another indicator"""
        if indicator_key not in row:
            return False
        if isinstance(value, str):
            return row[indicator_key] > row[value.lower()]
        else:
            return row[indicator_key] > value

    def _check_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator is below a value or another indicator"""
        if indicator_key not in row:
            return False
        
        # Get the indicator value and ensure it's numeric
        indicator_value = row[indicator_key]
        if indicator_value is None:
            return False
        
        # Convert indicator value to float if it's not already
        try:
            indicator_value = float(indicator_value)
        except (ValueError, TypeError):
            return False
        
        # Try to convert value to float/int first, if that fails treat as string indicator name
        try:
            # Try to convert to float first
            comparison_value = float(value)
            # If successful, compare directly
            return indicator_value < comparison_value
        except (ValueError, TypeError):
            # If conversion fails, treat as string indicator name
            value_key = str(value).lower()
            if value_key not in row:
                return False
            
            try:
                comparison_value = float(row[value_key])
                return indicator_value < comparison_value
            except (ValueError, TypeError):
                return False

    def _check_crosses_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator crosses above a value or another indicator"""
        if indicator_key not in row or f"{indicator_key}_prev" not in row:
            return False
        if isinstance(value, str):
            value_key = value.lower()
            if f"{value_key}_prev" not in row:
                return False
            return (row[indicator_key] > row[value_key]) and (row[f"{indicator_key}_prev"] <= row[f"{value_key}_prev"])
        else:
            return (row[indicator_key] > value) and (row[f"{indicator_key}_prev"] <= value)

    def _check_crosses_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator crosses below a value or another indicator"""
        if indicator_key not in row or f"{indicator_key}_prev" not in row:
            return False
        if isinstance(value, str):
            value_key = value.lower()
            if f"{value_key}_prev" not in row:
                return False
            return (row[indicator_key] < row[value_key]) and (row[f"{indicator_key}_prev"] >= row[f"{value_key}_prev"])
        else:
            return (row[indicator_key] < value) and (row[f"{indicator_key}_prev"] >= value)

    def _check_between(self, row: Dict[str, Any], indicator_key: str, value: List[Union[str, int, float]]) -> bool:
        """Check if indicator value is between two bounds"""
        if indicator_key not in row:
            return False
        try:
            if all(isinstance(x, (int, float)) for x in value):
                return value[0] <= row[indicator_key] <= value[1]
            else:
                lower_value = row[value[0].lower()] if isinstance(value[0], str) else value[0]
                upper_value = row[value[1].lower()] if isinstance(value[1], str) else value[1]
                return lower_value <= row[indicator_key] <= upper_value
        except (KeyError, TypeError):
            return False

    def _check_macd_cross(self, row: Dict[str, Any], comparison: str) -> bool:
        """Handle MACD specific crossing logic"""
        required_keys = ['macd', 'macd_signal', 'macd_prev', 'macdsignal_prev']
        if not all(key in row for key in required_keys):
            return False
            
        if comparison == "crosses_above":
            return (row['macd'] > row['macd_signal']) and (row['macd_prev'] <= row['macdsignal_prev'])
        else:  # crosses_below
            return (row['macd'] < row['macd_signal']) and (row['macd_prev'] >= row['macdsignal_prev'])

    def _check_bbands_cross(self, row: Dict[str, Any], comparison: str, value: str) -> bool:
        """Handle Bollinger Bands specific crossing logic"""
        value_key = value.lower() if isinstance(value, str) else value
        required_keys = ['close', 'close_prev', value_key]
        if not all(key in row for key in required_keys):
            return False
        
        if comparison == "crosses_above":
            return (row['close'] > row[value_key]) and (row['close_prev'] <= row[value_key])
        else:  # crosses_below
            return (row['close'] < row[value_key]) and (row['close_prev'] >= row[value_key])

    def _open_position(
        self, 
        portfolio: 'Portfolio', 
        symbol: str, 
        row: Dict[str, Any], 
        timestamp: datetime, 
        risk_mgmt: Dict
    ) -> Optional['Position']:
        """Open a new position using YAMLStrategy risk management"""
        
        entry_price = row.get('close', 0)
        if entry_price <= 0:
            self._log_trade_event('skip_entry', {
                'symbol': symbol,
                'price': entry_price,
                'shares': 0,
                'cost': 0.0,
                'cash_before': portfolio.cash,
                'cash_after': portfolio.cash,
                'total_value': portfolio.total_value,
                'reason': 'Invalid entry price (<= 0)',
                'conditions_met': False
            }, portfolio, timestamp)  # Pass the trade date
            return None
            
        # Calculate position size based on risk management
        risk_per_trade = risk_mgmt.get('risk_per_trade', 0.02)  # 2%
        max_position_size = risk_mgmt.get('max_position_size', 10000)
        
        # Calculate risk amount
        risk_amount = portfolio.cash * risk_per_trade
        
        # Calculate position size
        position_size = int(risk_amount / entry_price)
        
        if position_size <= 0:
            self._log_trade_event('skip_entry', {
                'symbol': symbol,
                'price': entry_price,
                'shares': 0,
                'cost': 0.0,
                'cash_before': portfolio.cash,
                'cash_after': portfolio.cash,
                'total_value': portfolio.total_value,
                'reason': f'Position size too small ({position_size} shares)',
                'conditions_met': False,
                'risk_management': {
                    'risk_per_trade': risk_per_trade,
                    'risk_amount': risk_amount,
                    'max_position_size': max_position_size
                }
            }, portfolio, timestamp)  # Pass the trade date
            return None
            
        total_cost = position_size * entry_price
        
        # Apply position size limits
        if total_cost > max_position_size:
            position_size = int(max_position_size / entry_price)
            total_cost = position_size * entry_price
            
        if portfolio.cash >= total_cost:
            cash_before = portfolio.cash
            portfolio.cash -= total_cost
            
            position = Position(
                symbol=symbol,
                shares=position_size,
                entry_price=entry_price,
                entry_time=timestamp,
                entry_value=total_cost
            )
            
            # FIXED: Add position to portfolio tracking
            portfolio.add_position(position)
            
            # Log the entry
            self._log_trade_event('entry', {
                'symbol': symbol,
                'price': entry_price,
                'shares': position_size,
                'cost': total_cost,
                'cash_before': cash_before,
                'cash_after': portfolio.cash,
                'total_value': portfolio.total_value,
                'reason': 'Entry conditions met',
                'conditions_met': True,
                'risk_management': {
                    'risk_per_trade': risk_per_trade,
                    'risk_amount': risk_amount,
                    'max_position_size': max_position_size,
                    'position_size': position_size
                }
            }, portfolio, timestamp)  # Pass the trade date
            
            return position
        else:
            self._log_trade_event('skip_entry', {
                'symbol': symbol,
                'price': entry_price,
                'shares': position_size,
                'cost': total_cost,
                'cash_before': portfolio.cash,
                'cash_after': portfolio.cash,
                'total_value': portfolio.total_value,
                'reason': f'Insufficient cash (need ${total_cost:.2f}, have ${portfolio.cash:.2f})',
                'conditions_met': False,
                'risk_management': {
                    'risk_per_trade': risk_per_trade,
                    'risk_amount': risk_amount,
                    'max_position_size': max_position_size,
                    'position_size': position_size
                }
            }, portfolio, timestamp)  # Pass the trade date
            
        return None

    def _close_position(
        self, 
        portfolio: 'Portfolio', 
        position: 'Position', 
        row: Dict[str, Any], 
        timestamp: datetime
    ) -> 'Trade':
        """Close an existing position"""
        
        exit_price = row.get('close', position.entry_price)
        exit_value = position.shares * exit_price
        
        # Debug: Log the position and exit details
        logger.debug(f"Closing position: {position.symbol} | Entry: ${position.entry_price:.2f} | Exit: ${exit_price:.2f} | Shares: {position.shares}")
        
        cash_before = portfolio.cash
        portfolio.cash += exit_value
        
        # Remove position from portfolio tracking
        portfolio.remove_position(position.symbol)
        
        # Calculate PnL
        pnl = exit_value - position.entry_value
        pnl_pct = (exit_price - position.entry_price) / position.entry_price
        
        # Create trade record
        trade = Trade(
            symbol=position.symbol,
            shares=position.shares,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=timestamp,
            pnl=pnl,
            pnl_pct=pnl_pct
        )
        
        # Log the exit with trade date
        self._log_trade_event('exit', {
            'symbol': position.symbol,
            'price': exit_price,
            'shares': position.shares,
            'cost': position.entry_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'cash_before': cash_before,
            'cash_after': portfolio.cash,
            'total_value': portfolio.total_value,
            'reason': 'Exit conditions met',
            'conditions_met': True
        }, portfolio, timestamp)
        
        return trade

    def _calculate_performance_metrics(
        self, 
        portfolio: 'Portfolio', 
        trades: List['Trade'], 
        initial_capital: float
    ) -> Dict[str, float]:
        """Calculate performance metrics"""
        
        if not trades:
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0
            }
            
        # Total return
        total_return = (portfolio.total_value - initial_capital) / initial_capital
        
        # Win rate
        winning_trades = sum(1 for trade in trades if trade.pnl > 0)
        win_rate = winning_trades / len(trades) if trades else 0
        
        # Profit factor
        gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in trades if trade.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calculate daily returns for Sharpe ratio and drawdown
        daily_returns = self._calculate_daily_returns(trades, initial_capital)
        
        # Sharpe ratio (simplified)
        if len(daily_returns) > 1:
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) if np.std(daily_returns) > 0 else 0
        else:
            sharpe_ratio = total_return / 0.15 if total_return > 0 else 0
        
        # Max drawdown
        max_drawdown = self._calculate_max_drawdown(daily_returns)
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor
        }

    def _calculate_daily_returns(self, trades: List['Trade'], initial_capital: float) -> List[float]:
        """Calculate daily returns from trades using Polars for efficiency"""
        if not trades:
            return [0.0]
            
        # Create Polars DataFrame from trades for efficient processing
        trades_data = [
            {
                'exit_date': trade.exit_time.date(),
                'pnl': trade.pnl
            }
            for trade in trades
        ]
        
        trades_df = pl.DataFrame(trades_data)
        
        # Group by date and sum P&L
        daily_pnl = trades_df.group_by('exit_date').agg(
            pl.col('pnl').sum().alias('daily_pnl')
        ).sort('exit_date')
        
        # Convert to returns
        daily_returns = []
        current_value = initial_capital
        
        for row in daily_pnl.iter_rows(named=True):
            daily_pnl_value = row['daily_pnl']
            current_value += daily_pnl_value
            daily_return = daily_pnl_value / (current_value - daily_pnl_value) if (current_value - daily_pnl_value) > 0 else 0
            daily_returns.append(daily_return)
            
        return daily_returns

    def _calculate_max_drawdown(self, daily_returns: List[float]) -> float:
        """Calculate maximum drawdown from daily returns"""
        if not daily_returns:
            return 0.0
            
        cumulative = np.cumprod(1 + np.array(daily_returns))
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        return float(np.min(drawdown))

    # Live trading methods (from the previous implementation)
    async def _run_live_trading(
        self, 
        strategy: Dict[str, Any], 
        mode: TradingMode, 
        user_id: str, 
        alpaca_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute live or paper trading mode"""
        logger.info(f"Starting {mode.value} trading for strategy: {strategy.get('name')}")
        
        # Initialize Alpaca client
        alpaca_client = await self._get_alpaca_client(alpaca_config, mode)
        
        # Start the trading loop
        trading_task = asyncio.create_task(
            self._trading_loop(strategy, mode, user_id, alpaca_client)
        )
        
        # Store the task for management
        self.active_trades[strategy.get('id')] = {
            'task': trading_task,
            'strategy': strategy,
            'mode': mode,
            'user_id': user_id,
            'alpaca_client': alpaca_client,
            'started_at': datetime.utcnow(),
            'status': 'running'
        }
        
        return {
            'status': 'started',
            'strategy_id': str(strategy.get('id')),
            'mode': mode.value,
            'message': f'{mode.value.title()} trading started for {strategy.get('name')}'
        }

    async def _trading_loop(
        self, 
        strategy: Dict[str, Any], 
        mode: TradingMode, 
        user_id: str, 
        alpaca_client: AlpacaDataFetcher
    ):
        """Main trading loop for live/paper trading"""
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
            
        symbols = config.get('symbols', [])
        timeframe = config.get('timeframe')
        
        logger.info(f"Trading loop started for {symbols}")
        
        try:
            while True:
                # Check if trading should continue
                if not await self._should_continue_trading(strategy.get('id')):
                    logger.info(f"Trading stopped for strategy {strategy.get('id')}")
                    break
                
                # Get current market data
                current_data = await self._get_current_market_data(
                    symbols, timeframe, alpaca_client
                )
                
                # Calculate indicators
                symbol_data = {}
                for symbol in symbols:
                    if symbol in current_data:
                        # Create indicator factory with strategy parameters
                        indicator_params = self._convert_indicators_to_params(config.get('indicators', []))
                        indicator_factory = IndicatorFactory(current_data[symbol], indicator_params)
                        symbol_data[symbol] = indicator_factory.get_indicators()
                
                # Execute trading logic
                await self._execute_live_trading_logic(
                    strategy, symbol_data, alpaca_client, mode
                )
                
                # Wait for next iteration
                await asyncio.sleep(self._get_sleep_time(timeframe))
                
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
            await self._update_trading_status(strategy.get('id'), 'error', str(e))
        finally:
            await self._update_trading_status(strategy.get('id'), 'stopped')

    async def _get_alpaca_client(
        self, 
        alpaca_config: Dict[str, Any], 
        mode: TradingMode
    ) -> AlpacaDataFetcher:
        """Get or create Alpaca client"""
        client_key = f"{mode.value}_{alpaca_config['api_key']}"
        
        if client_key not in self.alpaca_clients:
            # Determine endpoint based on mode
            if mode == TradingMode.PAPER:
                endpoint = alpaca_config.get('paper_endpoint', 'https://paper-api.alpaca.markets/v2')
            else:  # LIVE
                endpoint = alpaca_config.get('live_endpoint', 'https://api.alpaca.markets/v2')
            
            self.alpaca_clients[client_key] = AlpacaDataFetcher(
                api_key=alpaca_config['api_key'],
                secret_key=alpaca_config['secret_key'],
                base_url=endpoint
            )
            
        return self.alpaca_clients[client_key]

    async def _get_current_market_data(
        self, 
        symbols: List[str], 
        timeframe: str, 
        alpaca_client: AlpacaDataFetcher
    ) -> Dict[str, pl.DataFrame]:
        """Get current market data for symbols"""
        current_data = {}
        
        for symbol in symbols:
            try:
                # Get recent data (last 30 bars for indicators)
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=30)
                
                data = await alpaca_client.get_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=timeframe
                )
                
                if data is not None and len(data) > 0:
                    current_data[symbol] = data
                    
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                
        return current_data

    async def _execute_live_trading_logic(
        self, 
        strategy: Dict[str, Any], 
        symbol_data: Dict[str, pl.DataFrame], 
        alpaca_client: AlpacaDataFetcher,
        mode: TradingMode
    ):
        """Execute trading logic for live/paper trading"""
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
            
        entry_conditions = config.get('entry_conditions', [])
        exit_conditions = config.get('exit_conditions', [])
        risk_mgmt = config.get('risk_management')
        
        # Get current positions
        positions = await alpaca_client.get_positions()
        
        # Check exit conditions first
        for symbol, position in positions.items():
            if symbol in symbol_data:
                current_row = symbol_data[symbol].tail(1).to_dicts()[0]
                
                if self._check_exit_conditions(exit_conditions, current_row, symbol, position, datetime.utcnow()):
                    await self._close_live_position(alpaca_client, symbol, position)
        
        # Check entry conditions
        for symbol in config.get('symbols', []):
            if symbol not in positions and symbol in symbol_data:
                current_row = symbol_data[symbol].tail(1).to_dicts()[0]
                
                if self._check_entry_conditions(entry_conditions, current_row, symbol):
                    await self._open_live_position(
                        alpaca_client, symbol, current_row, risk_mgmt, mode
                    )

    async def _open_live_position(
        self, 
        alpaca_client: AlpacaDataFetcher, 
        symbol: str, 
        current_row: Dict[str, Any], 
        risk_mgmt: Dict,
        mode: TradingMode
    ):
        """Open a position using Alpaca API"""
        try:
            entry_price = current_row.get('close', 0)
            if entry_price <= 0:
                return
            
            # Get account information
            account = await alpaca_client.get_account()
            cash = float(account.get('cash', 0))
            
            # Calculate position size based on risk management
            risk_per_trade = risk_mgmt.get('risk_per_trade', 0.02)
            max_position_size = risk_mgmt.get('max_position_size', 10000)
            
            risk_amount = cash * risk_per_trade
            position_size = int(risk_amount / entry_price)
            
            if position_size <= 0:
                return
            
            total_cost = position_size * entry_price
            
            # Apply position size limits
            if total_cost > max_position_size:
                position_size = int(max_position_size / entry_price)
                total_cost = position_size * entry_price
            
            # Calculate stop loss and take profit
            stop_loss_price = entry_price * (1 - risk_mgmt.get('stop_loss', 0.05))
            take_profit_price = entry_price * (1 + risk_mgmt.get('take_profit', 0.10))
            
            # Place order with Alpaca
            order = await alpaca_client.place_order(
                symbol=symbol,
                qty=position_size,
                side='buy',
                type='market',
                time_in_force='day',
                stop_loss=stop_loss_price,
                take_profit=take_profit_price
            )
            
            logger.info(f"Opened position: {symbol} {position_size} shares at ${entry_price:.2f}")
            
        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}")

    async def _close_live_position(
        self, 
        alpaca_client: AlpacaDataFetcher, 
        symbol: str, 
        position: Dict[str, Any]
    ):
        """Close a position using Alpaca API"""
        try:
            qty = abs(float(position.get('qty', 0)))
            if qty <= 0:
                return
            
            # Place sell order
            order = await alpaca_client.place_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                type='market',
                time_in_force='day'
            )
            
            logger.info(f"Closed position: {symbol} {qty} shares")
            
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")

    async def _should_continue_trading(self, strategy_id: str) -> bool:
        """Check if trading should continue"""
        if strategy_id not in self.active_trades:
            return False
        
        status = self.active_trades[strategy_id]['status']
        return status == 'running'

    async def _update_trading_status(self, strategy_id: str, status: str, error: str = None):
        """Update trading status"""
        if strategy_id in self.active_trades:
            self.active_trades[strategy_id]['status'] = status
            if error:
                self.active_trades[strategy_id]['error'] = error

    def _get_sleep_time(self, timeframe: str) -> int:
        """Get sleep time between iterations based on timeframe"""
        sleep_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '1d': 86400
        }
        return sleep_map.get(timeframe, 300)  # Default to 5 minutes

    async def stop_trading(self, strategy_id: str) -> Dict[str, Any]:
        """Stop live/paper trading for a strategy"""
        if strategy_id not in self.active_trades:
            return {'status': 'not_found', 'message': 'No active trading found'}
        
        trading_info = self.active_trades[strategy_id]
        
        # Cancel the trading task
        if not trading_info['task'].done():
            trading_info['task'].cancel()
            try:
                await trading_info['task']
            except asyncio.CancelledError:
                pass
        
        # Close all positions
        try:
            positions = await trading_info['alpaca_client'].get_positions()
            for symbol, position in positions.items():
                await self._close_live_position(trading_info['alpaca_client'], symbol, position)
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
        
        # Remove from active trades
        del self.active_trades[strategy_id]
        
        return {
            'status': 'stopped',
            'message': f'Trading stopped for strategy {strategy_id}'
        }

    async def get_trading_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get current trading status"""
        if strategy_id not in self.active_trades:
            return {'status': 'not_found'}
        
        trading_info = self.active_trades[strategy_id]
        
        # Get current positions
        positions = {}
        try:
            positions = await trading_info['alpaca_client'].get_positions()
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
        
        return {
            'status': trading_info['status'],
            'mode': trading_info['mode'].value,
            'started_at': trading_info['started_at'].isoformat(),
            'positions': positions,
            'error': trading_info.get('error')
        }

    def _log_trade_event(self, event_type: str, details: Dict[str, Any], portfolio: 'Portfolio', trade_date: Optional[datetime] = None):
        """Log trade events with detailed information"""
        self.trade_counter += 1
        
        # Use the actual trade date if provided, otherwise use current time
        log_timestamp = trade_date.isoformat() if trade_date else datetime.now().isoformat()
        
        log_entry = {
            'trade_id': self.trade_counter,
            'timestamp': log_timestamp,
            'trade_date': trade_date.isoformat() if trade_date else None,  # Add specific trade date
            'event_type': event_type,  # 'entry', 'exit', 'skip_entry', 'skip_exit'
            'symbol': details.get('symbol', ''),
            'price': details.get('price', 0.0),
            'shares': details.get('shares', 0),
            'cost': details.get('cost', 0.0),
            'pnl': details.get('pnl', 0.0),
            'pnl_pct': details.get('pnl_pct', 0.0),
            'cash_before': details.get('cash_before', 0.0),
            'cash_after': details.get('cash_after', 0.0),
            'total_value': details.get('total_value', 0.0),
            'reason': details.get('reason', ''),
            'conditions_met': details.get('conditions_met', False),
            'risk_management': details.get('risk_management', {})
        }
        
        self.trade_log.append(log_entry)
        
        # Format the date for display
        date_str = trade_date.strftime('%Y-%m-%d') if trade_date else 'N/A'
        
        # Log to console with formatted output including date
        if event_type == 'entry':
            logger.info(f"🟢 TRADE #{self.trade_counter} - ENTRY: {details['symbol']} | "
                       f"Date: {date_str} | Price: ${details['price']:.2f} | Shares: {details['shares']} | "
                       f"Cost: ${details['cost']:.2f} | Cash: ${details['cash_after']:.2f}")
        elif event_type == 'exit':
            pnl_color = "🟢" if details['pnl'] > 0 else "🔴"
            logger.info(f"{pnl_color} TRADE #{self.trade_counter} - EXIT: {details['symbol']} | "
                       f"Date: {date_str} | Price: ${details['price']:.2f} | Shares: {details['shares']} | "
                       f"PnL: ${details['pnl']:.2f} ({details['pnl_pct']:.2%}) | "
                       f"Cash: ${details['cash_after']:.2f}")
        elif event_type == 'skip_entry':
            logger.info(f"⏭️  SKIP ENTRY: {details['symbol']} | "
                       f"Date: {date_str} | Price: ${details['price']:.2f} | Reason: {details['reason']} | "
                       f"Cash: ${details['cash_after']:.2f}")
        elif event_type == 'skip_exit':
            logger.info(f"⏭️  SKIP EXIT: {details['symbol']} | "
                       f"Date: {date_str} | Price: ${details['price']:.2f} | Reason: {details['reason']} | "
                       f"Cash: ${details['cash_after']:.2f}")

    def get_trade_log(self) -> List[Dict[str, Any]]:
        """Get the complete trade log"""
        return self.trade_log

    def print_trade_summary(self):
        """Print a summary of all trades"""
        if not self.trade_log:
            logger.info("No trades executed")
            return
        
        entries = [log for log in self.trade_log if log['event_type'] == 'entry']
        exits = [log for log in self.trade_log if log['event_type'] == 'exit']
        skips = [log for log in self.trade_log if log['event_type'] in ['skip_entry', 'skip_exit']]
        
        total_pnl = sum(log['pnl'] for log in exits)
        winning_trades = sum(1 for log in exits if log['pnl'] > 0)
        losing_trades = sum(1 for log in exits if log['pnl'] < 0)
        
        # Get date range
        trade_dates = [log['trade_date'] for log in self.trade_log if log['trade_date']]
        if trade_dates:
            start_date = min(trade_dates)
            end_date = max(trade_dates)
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = "N/A"
        
        logger.info("=" * 80)
        logger.info("TRADE SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Date Range: {date_range}")
        logger.info(f"Total Trade Events: {len(self.trade_log)}")
        logger.info(f"Entries: {len(entries)}")
        logger.info(f"Exits: {len(exits)}")
        logger.info(f"Skipped: {len(skips)}")
        logger.info(f"Total PnL: ${total_pnl:.2f}")
        logger.info(f"Winning Trades: {winning_trades}")
        logger.info(f"Losing Trades: {losing_trades}")
        if exits:
            win_rate = winning_trades / len(exits) * 100
            logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info("=" * 80)

    def _debug_data_structure(self, data: pl.DataFrame, symbols: List[str]):
        """Debug method to verify data structure and prices"""
        logger.info("=" * 60)
        logger.info("DEBUG: Data Structure Verification")
        logger.info("=" * 60)
        
        for symbol in symbols:
            symbol_data = data.filter(pl.col("symbol") == symbol)
            if len(symbol_data) > 0:
                logger.info(f"Symbol: {symbol}")
                logger.info(f"  Total rows: {len(symbol_data)}")
                logger.info(f"  Date range: {symbol_data['datetime'].min()} to {symbol_data['datetime'].max()}")
                logger.info(f"  Price range: ${symbol_data['close'].min():.2f} to ${symbol_data['close'].max():.2f}")
                
                # Show a few sample rows
                sample_data = symbol_data.head(3).select(["datetime", "close", "volume"])
                logger.info(f"  Sample data:")
                for row in sample_data.iter_rows(named=True):
                    logger.info(f"    {row['datetime']}: ${row['close']:.2f} (vol: {row['volume']})")
                logger.info("")
        
        # Check for any duplicate datetime-symbol combinations
        duplicates = data.group_by(["datetime", "symbol"]).count().filter(pl.col("count") > 1)
        if len(duplicates) > 0:
            logger.warning(f"Found {len(duplicates)} duplicate datetime-symbol combinations!")
            logger.warning(duplicates)
        
        logger.info("=" * 60)


class Portfolio:
    """Portfolio tracking class"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # Track open positions
        self.equity_history = []
        
    @property
    def total_value(self) -> float:
        """Calculate total portfolio value including cash and open positions"""
        total = self.cash
        
        # Add value of open positions
        for symbol, position in self.positions.items():
            # For backtesting, we'll use the entry price as current price
            # In live trading, you'd get the current market price
            position_value = position.shares * position.entry_price
            total += position_value
            
        return total
    
    def add_position(self, position: 'Position'):
        """Add a position to the portfolio"""
        self.positions[position.symbol] = position
        
    def remove_position(self, symbol: str):
        """Remove a position from the portfolio"""
        if symbol in self.positions:
            del self.positions[symbol]
        
    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Get equity curve data"""
        return [
            {
                'timestamp': datetime.now().isoformat(),
                'value': self.total_value,
                'cash': self.cash,
                'positions_value': self.total_value - self.cash
            }
        ]


class Position:
    """Represents an open trading position"""
    
    def __init__(
        self, 
        symbol: str, 
        shares: int, 
        entry_price: float, 
        entry_time: datetime,
        entry_value: float
    ):
        self.symbol = symbol
        self.shares = shares
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.entry_value = entry_value
        
    def get_days_held(self, current_time: datetime) -> int:
        """Calculates the number of days the position has been held."""
        return (current_time - self.entry_time).days


class Trade:
    """Represents a completed trade"""
    
    def __init__(
        self,
        symbol: str,
        shares: int,
        entry_price: float,
        exit_price: float,
        entry_time: datetime,
        exit_time: datetime,
        pnl: float,
        pnl_pct: float
    ):
        self.symbol = symbol
        self.shares = shares
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.pnl = pnl
        self.pnl_pct = pnl_pct
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'shares': self.shares,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat(),
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'duration_days': (self.exit_time - self.entry_time).days
        }
