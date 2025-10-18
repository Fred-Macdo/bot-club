"""
Standalone Lumibot Strategy - Decoupled from Application Infrastructure

Use this version for:
- Testing in Jupyter notebooks
- Running strategies without MongoDB
- Development and debugging
- Quick prototyping

No database, no user management, no infrastructure dependencies.
Just pass API keys and strategy configuration!
"""

from lumibot.strategies import Strategy
from lumibot.brokers import Alpaca
from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import polars as pl

logger = logging.getLogger(__name__)


class StandaloneStrategy(Strategy):
    """
    Standalone Lumibot Strategy - No Infrastructure Dependencies
    
    Features:
    - Independent portfolio tracking per strategy
    - Automatic position attribution via Lumibot
    - Built-in trade history
    - Real-time P&L calculation
    - DCA support with lot tracking
    - No database required
    - No user management required
    
    Usage:
        from lumibot.brokers import Alpaca
        from lumibot.traders import Trader
        
        # Create broker
        broker = Alpaca({
            "API_KEY": "your_key",
            "API_SECRET": "your_secret",
            "PAPER": True
        })
        
        # Define strategy
        strategy = StandaloneStrategy(
            broker=broker,
            parameters={
                "name": "My Test Strategy",
                "strategy_config": {...},
                "initial_capital": 10000,
                "data_provider": "yahoo"
            }
        )
        
        # Run it
        trader = Trader()
        trader.add_strategy(strategy)
        trader.run_all()
    """
    
    parameters = {
        "name": "Standalone Strategy",
        "strategy_config": None,
        "initial_capital": 10000,
        "data_provider": "yahoo",
        "enable_logging": True,
        "log_trades": True
    }
    
    def initialize(self):
        """Initialize strategy - called once when strategy starts"""
        
        # Basic info
        self.strategy_name = self.parameters.get("name", "Standalone Strategy")
        self.config = self.parameters["strategy_config"]
        self.data_provider = self.parameters.get("data_provider", "yahoo")
        self.initial_capital = self.parameters.get("initial_capital", 10000)
        
        # Logging options
        self.enable_logging = self.parameters.get("enable_logging", True)
        self.log_trades = self.parameters.get("log_trades", True)
        
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
        
        # Import utilities (lazy import to avoid circular dependencies)
        from ..indicators.indicator_factory import IndicatorFactory
        from ..utils.condition_checker import ConditionChecker
        from ..utils.indicator_converter import IndicatorConverter
        
        self.IndicatorFactory = IndicatorFactory
        self.condition_checker = ConditionChecker()
        self.indicator_converter = IndicatorConverter()
        
        # Set sleep time based on timeframe
        self.sleeptime = self._parse_timeframe_to_sleeptime(self.timeframe)
        
        # Track DCA entries per symbol
        self.dca_entry_count: Dict[str, int] = {}
        
        # In-memory trade log (if logging enabled)
        self.trade_log: List[Dict[str, Any]] = []
        self.entry_signals: List[Dict[str, Any]] = []
        
        logger.info(
            f"Initialized '{self.strategy_name}' "
            f"with ${self.initial_capital} capital, "
            f"symbols={self.symbols}, timeframe={self.timeframe}"
        )
    
    def on_trading_iteration(self):
        """Main trading loop - called every sleeptime interval"""
        try:
            # Get current portfolio status
            portfolio_value = self.get_portfolio_value()
            cash = self.get_cash()
            positions = self.get_positions()
            
            if self.enable_logging:
                logger.info(
                    f"{self.strategy_name}: "
                    f"Value=${portfolio_value:.2f}, Cash=${cash:.2f}, "
                    f"Positions={len(positions)}"
                )
            
            # Process each symbol
            for symbol in self.symbols:
                self._process_symbol(symbol)
            
        except Exception as e:
            logger.error(
                f"Error in {self.strategy_name} iteration: {e}",
                exc_info=True
            )
    
    def _process_symbol(self, symbol: str):
        """Process trading logic for a single symbol"""
        try:
            # Get current position
            position = self.get_position(symbol)
            
            # Get historical data
            bars = self.get_historical_prices(
                symbol,
                length=100,
                timeframe=self._lumibot_timeframe(self.timeframe)
            )
            
            if bars is None or bars.df.empty:
                logger.debug(f"No data available for {symbol}")
                return
            
            # Convert to Polars DataFrame
            df_data = self._bars_to_polars(bars, symbol)
            
            # Calculate indicators
            indicator_params = self.indicator_converter.convert_indicators_to_params(
                self.config.get("indicators", [])
            )
            
            indicator_factory = self.IndicatorFactory(df_data, indicator_params)
            df_with_indicators = indicator_factory.get_indicators()
            
            if df_with_indicators is None or df_with_indicators.is_empty():
                logger.debug(f"No indicators calculated for {symbol}")
                return
            
            # Get latest data point
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
        """Enter position using Lumibot"""
        try:
            current_price = latest_data.get('close', 0)
            if current_price <= 0:
                return
            
            # Calculate position size
            quantity = self._calculate_position_size(symbol, current_price)
            
            if quantity <= 0:
                logger.debug(f"Position size too small for {symbol}, skipping")
                return
            
            # Get bracket order prices
            stop_loss_price = None
            take_profit_price = None
            
            stop_loss_pct = self.risk_management.get('stop_loss')
            take_profit_pct = self.risk_management.get('take_profit')
            
            if stop_loss_pct:
                stop_loss_price = current_price * (1 - stop_loss_pct)
            
            if take_profit_pct:
                take_profit_price = current_price * (1 + take_profit_pct)
            
            # Create and submit order
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
                f"{self.strategy_name}: Entered {symbol} "
                f"with {quantity} shares at ${current_price:.2f}"
                f" (DCA entry {self.dca_entry_count[symbol]})"
            )
            
            # Log entry signal in memory
            if self.log_trades:
                self.entry_signals.append({
                    "symbol": symbol,
                    "timestamp": latest_data.get('datetime', datetime.utcnow()),
                    "price": float(current_price),
                    "quantity": quantity,
                    "stop_loss": stop_loss_price,
                    "take_profit": take_profit_price
                })
            
        except Exception as e:
            logger.error(f"Error entering position {symbol}: {e}", exc_info=True)
    
    def _exit_position(self, symbol: str, position, latest_data: Dict):
        """Exit position using Lumibot"""
        try:
            # Sell all shares
            order = self.create_order(
                asset=symbol,
                quantity=position.quantity,
                side="sell",
                order_type="market"
            )
            
            self.submit_order(order)
            
            # Reset DCA counter
            self.dca_entry_count[symbol] = 0
            
            # Calculate P&L
            exit_price = latest_data.get('close', 0)
            entry_price = position.avg_fill_price
            pnl = (exit_price - entry_price) * position.quantity
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            
            logger.info(
                f"{self.strategy_name}: Exited {symbol} "
                f"with {position.quantity} shares at ${exit_price:.2f} "
                f"(Entry: ${entry_price:.2f}, P&L: ${pnl:.2f}, {pnl_pct:.2f}%)"
            )
            
            # Log trade in memory
            if self.log_trades:
                self.trade_log.append({
                    "symbol": symbol,
                    "quantity": float(position.quantity),
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "entry_time": position.entered_time,
                    "exit_time": latest_data.get('datetime', datetime.utcnow()),
                    "pnl": float(pnl),
                    "pnl_pct": float(pnl_pct)
                })
            
        except Exception as e:
            logger.error(f"Error exiting position {symbol}: {e}", exc_info=True)
    
    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """Calculate position size based on risk management rules"""
        try:
            cash = self.get_cash()
            
            position_sizing = self.risk_management.get("position_sizing_method", "fixed")
            risk_per_trade = self.risk_management.get("risk_per_trade", 0.02)
            max_position_size = self.risk_management.get("max_position_size", 10000)
            
            if position_sizing == "risk_based":
                risk_amount = cash * risk_per_trade
                quantity = risk_amount / price
            elif position_sizing == "fixed":
                fixed_amount = min(cash * risk_per_trade, max_position_size)
                quantity = fixed_amount / price
            else:
                quantity = (cash * 0.02) / price
            
            # Cap at max position size
            max_quantity = max_position_size / price
            quantity = min(quantity, max_quantity)
            
            # Ensure we have enough cash
            if quantity * price > cash:
                quantity = cash / price
            
            return max(0, int(quantity))
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def _bars_to_polars(self, bars, symbol: str) -> pl.DataFrame:
        """Convert Lumibot bars to Polars DataFrame"""
        try:
            df = bars.df
            
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
        return timeframe
    
    def get_strategy_metrics(self) -> Dict[str, Any]:
        """Get comprehensive strategy performance metrics"""
        try:
            trades = self.get_trades()
            positions = self.get_positions()
            
            # Calculate metrics
            winning_trades = [t for t in trades if hasattr(t, 'get_profit') and t.get_profit() > 0]
            losing_trades = [t for t in trades if hasattr(t, 'get_profit') and t.get_profit() < 0]
            
            total_pnl = sum(t.get_profit() for t in trades if hasattr(t, 'get_profit'))
            
            return {
                "strategy_name": self.strategy_name,
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
                "trade_log": self.trade_log if self.log_trades else [],
                "entry_signals": self.entry_signals if self.log_trades else []
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy metrics: {e}", exc_info=True)
            return {
                "strategy_name": self.strategy_name,
                "error": str(e)
            }
    
    def on_abrupt_closing(self):
        """Called when strategy is stopped abruptly"""
        logger.info(f"{self.strategy_name} closing...")
        
        # Print summary
        metrics = self.get_strategy_metrics()
        logger.info(f"Final Portfolio Value: ${metrics.get('current_value', 0):.2f}")
        logger.info(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")
        logger.info(f"Total Trades: {metrics.get('total_trades', 0)}")
    
    def trace_stats(self, context, snapshot_before):
        """Override for custom stats tracking"""
        pass

