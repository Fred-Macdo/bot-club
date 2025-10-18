"""
Lumibot Strategy Wrapper for Individual Strategy Portfolio Tracking

Each strategy instance maintains independent:
- Position tracking
- Cash balance (virtual allocation)
- Trade history
- Performance metrics
- P&L calculation

Multiple strategies can run on same Alpaca account with isolated tracking.
"""

from lumibot.strategies import Strategy
from lumibot.brokers import Alpaca
from lumibot.entities.asset import Asset
from lumibot.entities.order import Order
from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import asyncio
import polars as pl

from ..indicators.indicator_factory import IndicatorFactory
from ..utils.condition_checker import ConditionChecker
from ..utils.indicator_converter import IndicatorConverter

logger = logging.getLogger(__name__)


class StrategyPortfolioTracker(Strategy):
    """
    Lumibot Strategy wrapper for per-strategy portfolio tracking
    
    Features:
    - Independent portfolio tracking per strategy
    - Automatic position attribution
    - Built-in trade history
    - Real-time P&L calculation
    - DCA support with lot tracking
    """
    
    parameters = {
        "strategy_id": None,
        "user_id": None,
        "strategy_config": None,
        "db": None,
        "initial_capital": 10000,
        "data_provider": "yahoo"
    }
    
    def initialize(self, parameters: Dict[str, Any] = None):
        """
        Initialize strategy with configuration
        Called once when strategy starts
        """
        if parameters:
            self.parameters.update(parameters)
        
        self.strategy_id = self.parameters["strategy_id"]
        self.user_id = self.parameters["user_id"]
        self.config = self.parameters["strategy_config"]
        self.db = self.parameters["db"]
        self.data_provider = self.parameters.get("data_provider", "yahoo")
        
        # Strategy-specific portfolio tracking (Lumibot manages this automatically)
        self.initial_capital = self.parameters["initial_capital"]
        
        # Extract strategy configuration
        self.symbols = self.config.get("symbols", [])
        self.timeframe = self.config.get("timeframe", "15Min")
        self.risk_management = self.config.get("risk_management", {})
        self.entry_conditions = self.config.get("entry_conditions", [])
        self.exit_conditions = self.config.get("exit_conditions", [])
        
        # DCA configuration
        self.dca_config = self.config.get('dollar_cost_averaging', {})
        self.dca_enabled = self.dca_config.get('enabled', False)
        self.max_dca_positions = self.dca_config.get('max_positions', 1)
        
        # Initialize utilities
        self.condition_checker = ConditionChecker()
        self.indicator_converter = IndicatorConverter()
        
        # Set sleep time based on timeframe
        self.sleeptime = self._parse_timeframe_to_sleeptime(self.timeframe)
        
        # Track DCA entries per symbol (for limit enforcement)
        self.dca_entry_count: Dict[str, int] = {}
        
        logger.info(
            f"Initialized strategy {self.strategy_id} "
            f"with ${self.initial_capital} capital, "
            f"symbols={self.symbols}, timeframe={self.timeframe}"
        )
    
    def on_trading_iteration(self):
        """
        Main trading loop - called every sleeptime interval
        Lumibot handles scheduling automatically
        """
        try:
            # Get current portfolio status (strategy-specific!)
            portfolio_value = self.get_portfolio_value()
            cash = self.get_cash()
            positions = self.get_positions()
            
            logger.info(
                f"Strategy {self.strategy_id}: "
                f"Value=${portfolio_value:.2f}, Cash=${cash:.2f}, "
                f"Positions={len(positions)}"
            )
            
            # Process each symbol in the strategy
            for symbol in self.symbols:
                self._process_symbol(symbol)
            
            # Log portfolio snapshot for equity curve
            self._log_portfolio_snapshot()
            
        except Exception as e:
            logger.error(
                f"Error in strategy {self.strategy_id} iteration: {e}",
                exc_info=True
            )
    
    def _process_symbol(self, symbol: str):
        """Process trading logic for a single symbol"""
        try:
            # Get current position for this symbol (strategy-specific!)
            position = self.get_position(symbol)
            
            # Get latest market data with enough history for indicators
            bars = self.get_historical_prices(
                symbol,
                length=100,  # Enough bars for most indicators
                timeframe=self._lumibot_timeframe(self.timeframe)
            )
            
            if bars is None or bars.df.empty:
                logger.debug(f"No data available for {symbol}")
                return
            
            # Convert to format for indicator calculation
            df_data = self._bars_to_polars(bars, symbol)
            
            # Calculate indicators
            indicator_params = self.indicator_converter.convert_indicators_to_params(
                self.config.get("indicators", [])
            )
            
            indicator_factory = IndicatorFactory(df_data, indicator_params)
            df_with_indicators = indicator_factory.get_indicators()
            
            if df_with_indicators is None or df_with_indicators.is_empty():
                logger.debug(f"No indicators calculated for {symbol}")
                return
            
            # Get latest row as dict
            latest_data = df_with_indicators.row(-1, named=True)
            
            # Check exit conditions first (if we have a position)
            if position:
                should_exit = self._check_exit_conditions(symbol, latest_data, position)
                if should_exit:
                    self._exit_position(symbol, position, latest_data)
                    return
            
            # Check entry conditions
            should_enter = self._check_entry_conditions(symbol, latest_data, position)
            if should_enter:
                self._enter_position(symbol, latest_data)
                
        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}", exc_info=True)
    
    def _check_entry_conditions(
        self,
        symbol: str,
        latest_data: Dict,
        position
    ) -> bool:
        """Check if entry conditions are met"""
        try:
            # If we have a position, check DCA rules
            if position:
                if not self.dca_enabled:
                    return False
                
                # Check if we've reached max DCA entries
                current_entries = self.dca_entry_count.get(symbol, 0)
                if current_entries >= self.max_dca_positions:
                    logger.debug(
                        f"Max DCA positions ({self.max_dca_positions}) "
                        f"reached for {symbol}"
                    )
                    return False
            
            # Use condition checker
            should_enter, reason, _ = self.condition_checker.check_entry_conditions(
                conditions=self.entry_conditions,
                row=latest_data
            )
            
            if should_enter:
                logger.info(f"Entry signal for {symbol}: {reason}")
            
            return should_enter
            
        except Exception as e:
            logger.error(f"Error checking entry conditions for {symbol}: {e}")
            return False
    
    def _check_exit_conditions(
        self,
        symbol: str,
        latest_data: Dict,
        position
    ) -> bool:
        """Check if exit conditions are met"""
        try:
            should_exit, reason, _ = self.condition_checker.check_exit_conditions(
                conditions=self.exit_conditions,
                row=latest_data,
                position={
                    'entry_price': position.avg_fill_price,
                    'quantity': position.quantity,
                    'entry_time': position.entered_time
                },
                current_time=latest_data.get('datetime', self.get_datetime())
            )
            
            if should_exit:
                logger.info(f"Exit signal for {symbol}: {reason}")
            
            return should_exit
            
        except Exception as e:
            logger.error(f"Error checking exit conditions for {symbol}: {e}")
            return False
    
    def _enter_position(self, symbol: str, latest_data: Dict):
        """
        Enter position using Lumibot
        Automatically tracked in strategy portfolio
        """
        try:
            current_price = latest_data.get('close', 0)
            if current_price <= 0:
                return
            
            # Calculate position size based on risk management
            quantity = self._calculate_position_size(symbol, current_price)
            
            if quantity <= 0:
                logger.debug(f"Position size too small for {symbol}, skipping")
                return
            
            # Get bracket order prices if configured
            stop_loss_price = None
            take_profit_price = None
            
            stop_loss_pct = self.risk_management.get('stop_loss')
            take_profit_pct = self.risk_management.get('take_profit')
            
            if stop_loss_pct:
                stop_loss_price = current_price * (1 - stop_loss_pct)
            
            if take_profit_pct:
                take_profit_price = current_price * (1 + take_profit_pct)
            
            # Create and submit order (Lumibot handles the rest!)
            order = self.create_order(
                asset=symbol,
                quantity=quantity,
                side="buy",
                order_type="market",
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price
            )
            
            self.submit_order(order)
            
            # Track DCA entry
            if symbol not in self.dca_entry_count:
                self.dca_entry_count[symbol] = 0
            self.dca_entry_count[symbol] += 1
            
            logger.info(
                f"Strategy {self.strategy_id}: Entered {symbol} "
                f"with {quantity} shares at ${current_price:.2f}"
                f" (DCA entry {self.dca_entry_count[symbol]})"
            )
            
            # Log to database
            asyncio.create_task(self._log_entry_signal(symbol, latest_data))
            
        except Exception as e:
            logger.error(f"Error entering position {symbol}: {e}", exc_info=True)
    
    def _exit_position(self, symbol: str, position, latest_data: Dict):
        """
        Exit position using Lumibot
        Automatically updates portfolio and records trade
        """
        try:
            # Sell all shares
            order = self.create_order(
                asset=symbol,
                quantity=position.quantity,
                side="sell",
                order_type="market"
            )
            
            self.submit_order(order)
            
            # Reset DCA counter for this symbol
            self.dca_entry_count[symbol] = 0
            
            # Calculate P&L (Lumibot tracks this, but we log it)
            exit_price = latest_data.get('close', 0)
            entry_price = position.avg_fill_price
            pnl = (exit_price - entry_price) * position.quantity
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            
            logger.info(
                f"Strategy {self.strategy_id}: Exited {symbol} "
                f"with {position.quantity} shares at ${exit_price:.2f} "
                f"(Entry: ${entry_price:.2f}, P&L: ${pnl:.2f}, {pnl_pct:.2f}%)"
            )
            
            # Log to database
            asyncio.create_task(self._log_trade(symbol, position, latest_data, pnl))
            
        except Exception as e:
            logger.error(f"Error exiting position {symbol}: {e}", exc_info=True)
    
    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """Calculate position size based on risk management rules"""
        try:
            # Get strategy's available cash (not account total!)
            cash = self.get_cash()
            
            position_sizing = self.risk_management.get("position_sizing_method", "fixed")
            risk_per_trade = self.risk_management.get("risk_per_trade", 0.02)
            max_position_size = self.risk_management.get("max_position_size", 10000)
            
            if position_sizing == "risk_based":
                # Calculate based on risk percentage
                risk_amount = cash * risk_per_trade
                quantity = risk_amount / price
            elif position_sizing == "fixed":
                # Fixed dollar amount per trade
                fixed_amount = min(cash * risk_per_trade, max_position_size)
                quantity = fixed_amount / price
            else:
                # Default to 2% of cash
                quantity = (cash * 0.02) / price
            
            # Cap at max position size
            max_quantity = max_position_size / price
            quantity = min(quantity, max_quantity)
            
            # Ensure we have enough cash
            if quantity * price > cash:
                quantity = cash / price
            
            return max(0, int(quantity))  # Return whole shares
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def _log_portfolio_snapshot(self):
        """Log portfolio snapshot for equity curve tracking"""
        try:
            snapshot = {
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
                "timestamp": self.get_datetime(),
                "portfolio_value": float(self.get_portfolio_value()),
                "cash": float(self.get_cash()),
                "positions_value": float(self.get_portfolio_value() - self.get_cash()),
                "positions": [
                    {
                        "symbol": pos.asset.symbol if hasattr(pos.asset, 'symbol') else str(pos.asset),
                        "quantity": float(pos.quantity),
                        "avg_price": float(pos.avg_fill_price) if hasattr(pos, 'avg_fill_price') else 0,
                        "current_price": float(self.get_last_price(pos.asset)),
                        "value": float(pos.quantity * self.get_last_price(pos.asset))
                    }
                    for pos in self.get_positions()
                ]
            }
            
            # Save to MongoDB asynchronously
            asyncio.create_task(
                self.db['portfolio_snapshots'].insert_one(snapshot)
            )
            
        except Exception as e:
            logger.error(f"Error logging portfolio snapshot: {e}")
    
    async def _log_entry_signal(self, symbol: str, latest_data: Dict):
        """Log entry signal to database"""
        try:
            await self.db['entry_signals'].insert_one({
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
                "symbol": symbol,
                "timestamp": latest_data.get('datetime', datetime.utcnow()),
                "price": float(latest_data.get('close', 0)),
                "mode": "paper"  # or "live" depending on config
            })
        except Exception as e:
            logger.error(f"Error logging entry signal: {e}")
    
    async def _log_trade(self, symbol: str, position, latest_data: Dict, pnl: float):
        """Log completed trade to database"""
        try:
            await self.db['trades'].insert_one({
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
                "symbol": symbol,
                "quantity": float(position.quantity),
                "entry_price": float(position.avg_fill_price),
                "exit_price": float(latest_data.get('close', 0)),
                "entry_time": position.entered_time,
                "exit_time": latest_data.get('datetime', datetime.utcnow()),
                "pnl": float(pnl),
                "mode": "paper"  # or "live"
            })
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
    
    def _bars_to_polars(self, bars, symbol: str) -> pl.DataFrame:
        """Convert Lumibot bars to Polars DataFrame"""
        try:
            df = bars.df
            
            # Convert to Polars format
            data = {
                'datetime': df.index.tolist(),
                'open': df['open'].tolist(),
                'high': df['high'].tolist(),
                'low': df['low'].tolist(),
                'close': df['close'].tolist(),
                'volume': df['volume'].tolist() if 'volume' in df.columns else [0] * len(df),
                'symbol': [symbol] * len(df)
            }
            
            return pl.DataFrame(data)
            
        except Exception as e:
            logger.error(f"Error converting bars to Polars: {e}")
            return pl.DataFrame()
    
    def _parse_timeframe_to_sleeptime(self, timeframe: str) -> str:
        """Convert timeframe to Lumibot sleeptime format"""
        if "Min" in timeframe:
            minutes = timeframe.replace("Min", "")
            return f"{minutes}M"
        elif "Hour" in timeframe:
            hours = int(timeframe.replace("Hour", ""))
            return f"{hours * 60}M"
        elif "Day" in timeframe:
            return "1D"
        return "15M"
    
    def _lumibot_timeframe(self, timeframe: str) -> str:
        """Convert to Lumibot timeframe format"""
        # Lumibot uses formats like "1Min", "5Min", "1Hour", "1Day"
        return timeframe
    
    def get_strategy_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive strategy performance metrics
        Leverages Lumibot's built-in tracking
        """
        try:
            trades = self.get_trades()
            positions = self.get_positions()
            
            # Calculate metrics
            winning_trades = [t for t in trades if hasattr(t, 'get_profit') and t.get_profit() > 0]
            losing_trades = [t for t in trades if hasattr(t, 'get_profit') and t.get_profit() < 0]
            
            total_pnl = sum(t.get_profit() for t in trades if hasattr(t, 'get_profit'))
            
            return {
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
                "initial_capital": float(self.initial_capital),
                "current_value": float(self.get_portfolio_value()),
                "cash": float(self.get_cash()),
                "total_return_pct": (
                    (self.get_portfolio_value() - self.initial_capital) 
                    / self.initial_capital * 100
                ),
                "total_pnl": float(total_pnl),
                "positions_count": len(positions),
                "open_positions": [
                    {
                        "symbol": pos.asset.symbol if hasattr(pos.asset, 'symbol') else str(pos.asset),
                        "quantity": float(pos.quantity),
                        "avg_price": float(pos.avg_fill_price) if hasattr(pos, 'avg_fill_price') else 0
                    }
                    for pos in positions
                ],
                "total_trades": len(trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0,
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy metrics: {e}", exc_info=True)
            return {
                "strategy_id": self.strategy_id,
                "error": str(e)
            }
    
    def on_abrupt_closing(self):
        """Called when strategy is stopped abruptly"""
        logger.info(f"Strategy {self.strategy_id} closing abruptly, cleaning up...")
        # Lumibot handles most cleanup automatically
    
    def trace_stats(self, context, snapshot_before):
        """Override to add custom stats tracking"""
        # TODO: Implement custom performance tracking here
        pass