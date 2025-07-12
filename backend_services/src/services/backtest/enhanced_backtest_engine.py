import asyncio
import logging
import polars as pl
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Literal
import yfinance as yf
from enum import Enum
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.backtest import BacktestParams, BacktestResult
from ..indicators.IndicatorFactory import IndicatorFactory
from ..data_retrieval.alpaca_data_fetcher import AlpacaDataFetcher


logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading execution modes"""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class EnhancedBacktestEngine:
    """
    Enhanced backtesting engine with Lumibot-inspired trading logic
    Includes better position sizing, order execution, and market condition handling
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, **kwargs):
        self.data_cache = {}  # Cache for historical data
        self.alpaca_clients = {}  # Cache for Alpaca clients
        self.active_trades = {}
        self.db = db
        
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
        
        # Get strategy from database
        strategy = await self._get_strategy_from_db(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        if mode == TradingMode.BACKTEST:
            if not backtest_params:
                raise ValueError("Backtest parameters required for backtest mode")
            return await self._run_enhanced_backtest(strategy, backtest_params)
        
        elif mode in [TradingMode.PAPER, TradingMode.LIVE]:
            if not alpaca_config:
                raise ValueError("Alpaca configuration required for live/paper trading")
            return await self._run_live_trading(strategy, mode, user_id, alpaca_config)
        
        else:
            raise ValueError(f"Invalid trading mode: {mode}")

    async def _run_enhanced_backtest(self, strategy: Dict[str, Any], params: BacktestParams) -> BacktestResult:
        """Execute enhanced backtest with Lumibot-inspired logic"""
        logger.info(f"Running enhanced backtest for strategy: {strategy.get('name')}")
        
        # Get strategy configuration
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
        
        # Initialize enhanced portfolio
        portfolio = EnhancedPortfolio(initial_capital=params.initial_capital)
        
        # Execute enhanced strategy
        trades = await self._execute_enhanced_strategy(strategy, data, portfolio)
        
        # Calculate performance metrics
        metrics = self._calculate_performance_metrics(
            portfolio, 
            trades, 
            params.initial_capital
        )
        
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
        
        logger.info(f"Enhanced backtest completed: {len(trades)} trades, {metrics['total_return']:.2%} return")
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
            
            # Sort by datetime and symbol
            combined_data = combined_data.sort(["datetime", "symbol"])
            
            # Cache the data
            self.data_cache[cache_key] = combined_data
            
            logger.info(f"Retrieved {len(combined_data)} data points")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise

    async def _execute_enhanced_strategy(
        self, 
        strategy: Dict[str, Any], 
        data: pl.DataFrame, 
        portfolio: 'EnhancedPortfolio'
    ) -> List['EnhancedTrade']:
        """Execute the enhanced trading strategy with Lumibot-inspired logic"""
        logger.info(f"Executing enhanced strategy with {len(data)} data points")
        
        config = strategy.get('strategy_config') or strategy.get('yaml_config') or strategy.get('config')
        if not config:
            raise ValueError("No strategy configuration found")
            
        entry_conditions = config.get('entry_conditions', [])
        exit_conditions = config.get('exit_conditions', [])
        risk_mgmt = config.get('risk_management', {})
        
        trades = []
        open_positions = {}
        
        # Calculate indicators for each symbol
        symbol_data = {}
        for symbol in config.get('symbols', []):
            symbol_df = data.filter(pl.col("symbol") == symbol)
            if len(symbol_df) > 0:
                # Create indicator factory with strategy parameters
                indicator_params = self._convert_indicators_to_params(config.get('indicators', []))
                indicator_factory = IndicatorFactory(symbol_df, indicator_params)
                symbol_data[symbol] = indicator_factory.get_indicators()
                
                if symbol_data[symbol] is not None and len(symbol_data[symbol]) > 0:
                    logger.info(f"Calculated indicators for {symbol}: {symbol_data[symbol].columns}")
        
        # Process each data point with enhanced logic
        for i, row in enumerate(data.iter_rows(named=True)):
            current_symbol = row.get('symbol', config.get('symbols', [config.get('symbols', [])[0]])[0])
            current_datetime = row['datetime']
            
            # Get indicator data for current symbol
            if current_symbol not in symbol_data:
                continue
                
            symbol_indicators = symbol_data[current_symbol]
            current_row_idx = symbol_indicators.filter(
                pl.col("datetime") == current_datetime
            )
            
            if len(current_row_idx) == 0:
                continue
                
            current_row = current_row_idx.to_dicts()[0]
            
            # Enhanced exit logic - check all positions
            for symbol, position in list(open_positions.items()):
                if self._check_enhanced_exit_conditions(exit_conditions, current_row, symbol, position, current_datetime, portfolio):
                    trade = self._close_enhanced_position(portfolio, position, row, current_datetime)
                    trades.append(trade)
                    del open_positions[symbol]
                    logger.info(f"Closed position for {symbol} at {current_datetime}")
                    
            # Enhanced entry logic - only if we have cash and no position
            if current_symbol not in open_positions and portfolio.cash > 0:
                if self._check_enhanced_entry_conditions(entry_conditions, current_row, current_symbol, portfolio):
                    position = self._open_enhanced_position(
                        portfolio, 
                        current_symbol, 
                        row, 
                        current_datetime, 
                        risk_mgmt
                    )
                    if position:
                        open_positions[current_symbol] = position
                        logger.info(f"Opened position for {current_symbol} at {current_datetime}")
                        
        # Close any remaining open positions at the end
        final_row = data.tail(1).to_dicts()[0]
        final_datetime = final_row['datetime']
        for symbol, position in open_positions.items():
            trade = self._close_enhanced_position(portfolio, position, final_row, final_datetime)
            trades.append(trade)
            logger.info(f"Closed final position for {symbol}")
            
        return trades

    def _convert_indicators_to_params(self, indicators: List[Dict]) -> Dict:
        """Convert strategy indicators to IndicatorFactory parameters"""
        params = {}
        for indicator in indicators:
            name = indicator.get('name', '').lower()
            indicator_params = indicator.get('params', {})
            if name == 'sma':
                params['sma'] = {'period': indicator_params.get('period', 20)}
            elif name == 'ema':
                params['ema'] = {'period': indicator_params.get('period', 20)}
            elif name == 'rsi':
                params['rsi'] = {'period': indicator_params.get('period', 14)}
            elif name == 'bollinger_bands':
                params['bollinger_bands'] = {
                    'period': indicator_params.get('period', 20),
                    'std_dev': indicator_params.get('std_dev', 2)
                }
            elif name == 'atr':
                params['atr'] = {'period': indicator_params.get('period', 14)}
            elif name == 'adx':
                params['adx'] = {'period': indicator_params.get('period', 14)}
            elif name == 'obv':
                params['obv'] = {}
            elif name == 'mfi':
                params['mfi'] = {'period': indicator_params.get('period', 14)}
            elif name == 'cci':
                params['cci'] = {'period': indicator_params.get('period', 20)}
            elif name == 'vwap':
                params['vwap'] = {'period': indicator_params.get('period', 5)}
        return params

    def _check_enhanced_entry_conditions(
        self, 
        conditions: List[Dict], 
        row: Dict[str, Any], 
        symbol: str,
        portfolio: 'EnhancedPortfolio'
    ) -> bool:
        """Enhanced entry condition checking with portfolio awareness"""
        if not conditions:
            return False
            
        # Check if we have enough cash for a minimum position
        if portfolio.cash < 100:  # Minimum position size
            return False
            
        # Check if we're not over-leveraged
        if len(portfolio.positions) >= 5:  # Max 5 concurrent positions
            return False
            
        return all(
            self._check_condition(row, condition)
            for condition in conditions
        )

    def _check_enhanced_exit_conditions(
        self, 
        conditions: List[Dict], 
        row: Dict[str, Any], 
        symbol: str, 
        position: 'EnhancedPosition',
        current_time: datetime,
        portfolio: 'EnhancedPortfolio'
    ) -> bool:
        """Enhanced exit condition checking with position tracking"""
        if not conditions:
            # Enhanced default exit conditions
            current_price = row.get('close', position.entry_price)
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            
            # Exit after 8% profit or 4% loss (tighter than before)
            if pnl_pct > 0.08 or pnl_pct < -0.04:
                return True
                
            # Exit after 3 days (shorter holding period)
            if position.get_days_held(current_time) > 3:
                return True
                
            return False
            
        return any(
            self._check_condition(row, condition)
            for condition in conditions
        )

    def _check_condition(self, row: Dict[str, Any], condition_config: Dict) -> bool:
        """Check entry/exit condition using enhanced logic"""
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
        if isinstance(value, str):
            return row[indicator_key] < row[value.lower()]
        else:
            return row[indicator_key] < value

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

    def _open_enhanced_position(
        self, 
        portfolio: 'EnhancedPortfolio', 
        symbol: str, 
        row: Dict[str, Any], 
        timestamp: datetime, 
        risk_mgmt: Dict
    ) -> Optional['EnhancedPosition']:
        """Open a new position with enhanced risk management"""
        
        entry_price = row.get('close', 0)
        if entry_price <= 0:
            return None
            
        # Enhanced position sizing based on risk management
        risk_per_trade = risk_mgmt.get('risk_per_trade', 0.02)  # 2%
        max_position_size = risk_mgmt.get('max_position_size', 5000)  # Reduced from 10000
        min_position_size = risk_mgmt.get('min_position_size', 100)   # Minimum position
        
        # Calculate risk amount
        risk_amount = portfolio.cash * risk_per_trade
        
        # Calculate position size with minimum check
        position_size = int(risk_amount / entry_price)
        
        if position_size <= 0:
            return None
            
        total_cost = position_size * entry_price
        
        # Apply position size limits
        if total_cost > max_position_size:
            position_size = int(max_position_size / entry_price)
            total_cost = position_size * entry_price
        elif total_cost < min_position_size:
            position_size = int(min_position_size / entry_price)
            total_cost = position_size * entry_price
            
        if portfolio.cash >= total_cost:
            portfolio.cash -= total_cost
            position = EnhancedPosition(
                symbol=symbol,
                shares=position_size,
                entry_price=entry_price,
                entry_time=timestamp,
                entry_value=total_cost
            )
            return position
            
        return None

    def _close_enhanced_position(
        self, 
        portfolio: 'EnhancedPortfolio', 
        position: 'EnhancedPosition', 
        row: Dict[str, Any], 
        timestamp: datetime
    ) -> 'EnhancedTrade':
        """Close an existing position with enhanced tracking"""
        
        exit_price = row.get('close', position.entry_price)
        exit_value = position.shares * exit_price
        
        portfolio.cash += exit_value
        
        # Create enhanced trade record
        trade = EnhancedTrade(
            symbol=position.symbol,
            shares=position.shares,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=timestamp,
            pnl=exit_value - position.entry_value,
            pnl_pct=(exit_price - position.entry_price) / position.entry_price
        )
        
        return trade

    def _calculate_performance_metrics(
        self, 
        portfolio: 'EnhancedPortfolio', 
        trades: List['EnhancedTrade'], 
        initial_capital: float
    ) -> Dict[str, float]:
        """Calculate enhanced performance metrics"""
        
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

    def _calculate_daily_returns(self, trades: List['EnhancedTrade'], initial_capital: float) -> List[float]:
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

    async def _run_live_trading(self, strategy: Dict[str, Any], mode: TradingMode, user_id: str, alpaca_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute live or paper trading mode"""
        logger.info(f"Starting {mode.value} trading for strategy: {strategy.get('name')}")
        
        # This would integrate with live trading capabilities
        # For now, return a placeholder
        return {
            'status': 'not_implemented',
            'message': 'Live trading not yet implemented'
        }


class EnhancedPortfolio:
    """Enhanced portfolio tracking class with better position management"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}
        self.equity_history = []
        
    @property
    def total_value(self) -> float:
        return self.cash
        
    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Get equity curve data"""
        return [
            {
                'timestamp': datetime.now().isoformat(),
                'value': self.total_value,
                'cash': self.cash
            }
        ]


class EnhancedPosition:
    """Enhanced position tracking with better risk management"""
    
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


class EnhancedTrade:
    """Enhanced trade tracking with better metrics"""
    
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