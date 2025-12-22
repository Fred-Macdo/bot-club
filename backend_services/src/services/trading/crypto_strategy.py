from lumibot.strategies import Strategy
from lumibot.entities import Asset, Position
from lumibot.backtesting import YahooDataBacktesting, AlpacaBacktesting, PolygonDataBacktesting
from lumibot.brokers import Alpaca

from datetime import datetime
import pandas as pd
from typing import Dict, Union, List, Any
import numpy as np
import polars as pl
import logging

from ..indicators.indicator_factory import IndicatorFactory
from ..utils.condition_checker import ConditionChecker
from ..utils.indicator_converter import IndicatorConverter
from ..utils.trade_logger import TradeLogger
from ..utils.portfolio_manager import Portfolio, Position, Trade
from .strategy_persistence import StrategyPersistence
import json
logger = logging.getLogger(__name__)

# Set consistent formatting options at the beginning of the script
pd.set_option('display.precision', 2)
np.set_printoptions(precision=2, suppress=True)  # Added suppress=True to avoid scientific notation


class CryptoStrategy(Strategy):
    """
    This class takes in a yaml configuration file as a strategy and runs it using Lumibot lifecycle methods. 

    Args:
        strategy_config: Dict[str, Any] - The strategy configuration
            - symbols: List[str] - The symbols to trade
            - timeframe: str - The timeframe to trade
            - indicators: List[Dict[str, Any]] - The indicators to use
            - entry_conditions: List[Dict[str, Any]] - The entry conditions to use
            - exit_conditions: List[Dict[str, Any]] - The exit conditions to use
            - risk_management: Dict[str, Any] - The risk management to use
            - dca_enabled: bool - Whether to use DCA
            - max_dca_positions: int - The maximum number of DCA positions
    """
    def initialize(self,
                   strategy_config: Dict[str, Any],
                   event_queue=None,
                   strategy_id=None,
                   db=None,
                   user_id=None,
                   stream_publisher=None):
        
        self.indicator_converter = IndicatorConverter()
        self.strategy = strategy_config.get("config")
        self.symbols = self.strategy.get('symbols', [])
        self.timeframe = self.strategy.get('timeframe', '15Min')
        self.sleeptime = '10S'
        self.params = self.indicator_converter.convert_indicators_to_params(self.strategy.get('indicators', []))
        self.entry_conditions = self.strategy.get('entry_conditions', [])
        self.exit_conditions = self.strategy.get('exit_conditions', [])
        self.risk_management = self.strategy.get('risk_management', {})
        self.set_market("24/7")
        self.portfolio = Portfolio()
        self.portfolio.set_initial_capital(self.get_cash())
        self.condition_checker = ConditionChecker()
        self.persistence = StrategyPersistence(db=db, 
                                               strategy_id=strategy_id, 
                                               user_id=user_id)
        
        # Store event queue and strategy_id for emitting events
        self.event_queue = event_queue
        self.stream_publisher = stream_publisher
        self.strategy_id = strategy_id
        self.db = db
        self.user_id = user_id
        self.trade_counter = 0

    def log_message(self, message, level='info', color=None, broadcast=True):
        # Fix: Do not pass 'broadcast' to the parent method
        super().log_message(message, level, color)
        
        if broadcast and hasattr(self, 'stream_publisher') and self.stream_publisher:
             self.stream_publisher("log", {
                "timestamp": datetime.now().timestamp() * 1000, 
                "level": str(level).upper(), 
                "message": str(message)
            })

    def _emit_log(self, message, level="INFO"):
        self.log_message(message, level=level)
    
    def on_trading_iteration(self):


        # Get the cash balance, positions, and portfolio value
        cash = self.get_cash()
        positions = self.get_positions()
        self.log_message(f"Date: {self.get_datetime()}")
        self.log_message(f"Cash Balance: {cash:.2f}")
        self.log_message(f"Current Positions: {positions}")
        self.log_message(f"Account Value: {self.get_portfolio_value():.2f}")
        # If the cash balance is less than 0, sell all positions and sleep
        # 1. Get the assets
        # 2. Get the last price for each asset
        # 3. Get the data for each asset
        # 4. Calculate the indicators for each asset
        # 5. Check the exit conditions for each asset
        # 6. If we have a position, check if the exit conditions are met, if so; sell all positions for that asset
        # 7. if we have a position, check if the stop loss is hit, if so; sell all positions for that asset
        # 8. if we have a position, check if the take profit is hit, if so; sell all positions for that asset
        # 9. if we have a position, check if the DCA entry conditions are met, if so; buy the asset
        # 10. If we don't have a position, check if the entry conditions are met, if so; buy the asset

        # 1. Get the assets
        self.log_message("Getting assets")
        self.log_message(f"Symbols: {self.symbols}")
        self.log_message(f"Params: {self.params}")
        assets = [Asset(x, asset_type=Asset.AssetType.CRYPTO) for x in self.symbols]
        for asset in assets: 
            # 2. Get the last price for each asset
            base = asset
            quote = Asset(symbol="USD", asset_type=Asset.AssetType.FOREX)
            
            #  3. Get data for each symbol
            prices = self.get_historical_prices(base, 50, self.timeframe, quote=quote)
           
            prices.df["symbol"] = asset.symbol
            position = self.get_position(asset)
            prices_df = pl.from_pandas(prices.df)
            # 4. Calculate the indicators for each asset
            technicals = IndicatorFactory(prices_df, self.params)
            df = technicals.calculate_indicators()

            if df is None or df.is_empty():
                self.log_message(f"No indicators calculated for {asset.symbol}")
                continue
            else:
                self.log_message(f"Indicators calculated for {asset.symbol}")

                # Round the last n rows and convert to pandas for pretty printing
                n_rows = 2
                df_to_log = (
                    df.tail(n_rows)
                      .with_columns(pl.col(pl.Float64).round(4))
                      .to_pandas()
                )

                # Build a table-style string
                indicator_table = df_to_log.to_string(index=False)

                self.log_message(
                    f"Technical indicators (last {n_rows} rows):\n" + indicator_table
                )

                # Keep the JSON payload for the frontend to render as a table if needed
                df_json_string = df_to_log.to_json(orient="records")
                df_data = json.loads(df_json_string)
                log_payload = {
                    "type": "dataframe",
                    "title": f"Technical Indicators for {asset.symbol}",
                    "data": df_data
                }
                self.log_message(json.dumps(log_payload, indent=4))

                latest_data = df.row(-1, named=True)
                entry_conditions, entry_data_context = self._check_entry_conditions(latest_data)
            self.log_message(f"Position: {position}, type: {type(position)}")
            if position:
                # 5. IF WE HAVE A POSITION, CHECK THE EXIT CONDITIONS
                exit_conditions, exit_reason, exit_data_context = self._check_exit_conditions(latest_data, asset)
                if exit_conditions:
                    self.log_message(f"Exit conditions met for {asset.symbol}: {exit_reason}")
                    self._emit_log(f"🔴 EXIT: {asset.symbol} - {exit_reason}", "WARNING")
                    self.log_message(f"Exit data context: {exit_data_context}")
                    self.log_message(f"Exit conditions: {exit_conditions}")
                    self.log_message(f"Exit reason: {exit_reason}")
                    self.log_message(f"Exit data context: {exit_data_context}")
                    # 6. EVALUATES TO TRUE OR FALSE, IF TRUE SELL ALL
                    order = self.create_order(
                        asset=base,
                        quantity=position.quantity,
                        side="sell",
                        quote=quote
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    
                    # Get completed trades from portfolio
                    completed_trades = self.portfolio.sell(asset.symbol, position.quantity, latest_data['close'], self.get_datetime())
                    
                    # Emit completed trades with full P&L details
                    for trade in completed_trades:
                        self._emit_completed_trade(trade)
                        self._emit_log(f"📈 TRADE CLOSED: {trade.symbol} | P&L: ${trade.pnl:.2f}")
                    
                    # Also emit simple transaction event for real-time feedback
                    self._emit_trade_event("sell", asset.symbol, position.quantity, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()
                
                # 9. if we have a position, check if the DCA entry conditions are met, 
                #    if so; buy the asset
                
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")  
                    self._emit_log(f"🟢 DCA ENTRY: {asset.symbol}")
                    self.log_message(f"Entry conditions: {entry_conditions}")
                    self.log_message(f"Entry data context: {entry_data_context}")
                    # 10. EVALUATES TO TRUE OR FALSE, IF TRUE BUY THE ASSET
                    position_size = self._calculate_position_size(asset, latest_data)
                    position_size = max(self.risk_management.get('max_position_size', 10000), int(position_size))
                    quote = Asset("USD", asset_type="forex")

                    order = self.create_order(
                        asset=base,
                        quantity=position_size,
                        side="buy",
                        quote=quote
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    #avg_fill_price = self.get_order(order).avg_fill_price
                    new_position = self.portfolio.add_buy(asset.symbol, position_size, latest_data['close'], self.get_datetime())
                    self._emit_log(f"✅ BUY: {position_size} {asset.symbol} @ ${latest_data['close']:.2f}")
                    
                    # Emit trade and position events
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()
            # 10. If we don't have a position, check if the entry conditions are met, if so; buy the asset
            else:
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")
                    self._emit_log(f"🟢 ENTRY: {asset.symbol} conditions met")
                    self.log_message(f"Entry conditions: {entry_conditions}")
                    self.log_message(f"Entry data context: {entry_data_context}")
                    # 10. EVALUATES TO TRUE OR FALSE, IF TRUE BUY THE ASSET
                    position_size = self._calculate_position_size(asset, latest_data)
                    position_size = max(self.risk_management.get('max_position_size', 10000), int(position_size))
                    quote = Asset("USD", asset_type="forex")

                    order = self.create_order(
                        asset=base,
                        quantity=position_size,
                        side="buy",
                        quote=quote
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    #avg_fill_price = self.get_order(order).avg_fill_price
                    new_position = self.portfolio.add_buy(asset.symbol, position_size, latest_data['close'], self.get_datetime())
                    self.log_message(f"New Position: {new_position}")
                    self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df['close'][-1]:.2f}")
                    self._emit_log(f"✅ BUY: {position_size} {asset.symbol} @ ${latest_data['close']:.2f}")

                    # Emit trade and position events
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()

        self.log_message("Saving portfolio snapshot to DB")
        self.log_message(f"Portfolio snapshot: {self.portfolio.model_dump_json()}")

        self.log_message("**********************************************************************************")
        self.log_message("**********************************************************************************")
        self.log_message("**********************************************************************************")
        self.log_message("**********************************************************************************")
        self.log_message("**********************************************************************************")

    def on_abrupt_closing(self):
        # Sell all positions
        self.sell_all()

    ######################################
    ########## HELPER FUNCTIONS ##########
    ######################################

    def _check_entry_conditions(self, row: pd.Series) -> bool:
        """Check if all entry conditions are met"""
        
        return self.condition_checker.check_entry_conditions(conditions=self.entry_conditions, row=row)

    def _check_exit_conditions(self, row: pd.Series, asset: Asset) -> bool:
        """Check if any exit condition is met"""
        return self.condition_checker.check_exit_conditions(conditions=self.exit_conditions, 
                                                       row=row,
                                                       position=self.get_position(asset), 
                                                       current_time=self.get_datetime())
    
    def _calculate_position_size(self, asset: Asset, latest_data: Dict[str, Any]) -> float:
        """Calculates position size based on risk management settings."""
        close_price = latest_data.get('close')
        cash = self.get_cash()
        if not close_price or close_price <= 0:
            self.log_message("Invalid close price for position sizing.")
            return 0.0
        max_position_size = self.risk_management.get('max_position_size', 10000)

        method = self.risk_management.get('method', 'risk_based')
        risk_per_trade = self.risk_management.get('risk_per_trade', .01)  # Default to 1%
        
        self.log_message(f"Final risk per trade: {risk_per_trade:.4f} using method: {method}")
        
        amount_to_risk = cash * risk_per_trade
        self.log_message(f"Amount to risk: {amount_to_risk:.2f} = ${cash:.2f} * {risk_per_trade:.4f}%")
        if method == 'risk_based':
            # Simple risk-based: risk a percentage of portfolio
            return amount_to_risk / close_price

        elif method == 'atr_based':
            # ATR-based: position size is based on volatility (ATR)
            atr_multiplier = self.risk_management.get('atr_multiplier', 2.0) # Default to 2
            atr_key = next((key for key in latest_data if 'atr' in key.lower()), None)
            
            if not atr_key or latest_data.get(atr_key) is None:
                self.log_message("ATR not found or is None in data, falling back to risk_based sizing.")
                # Fallback to simple risk-based sizing
                return amount_to_risk / close_price

            atr_value = latest_data[atr_key]
            stop_loss_distance = atr_value * atr_multiplier

            if stop_loss_distance > 0:
                # quantity = amount to risk / (distance to stop loss per share)
                return amount_to_risk / stop_loss_distance
            else:
                self.log_message("ATR stop loss distance is zero or negative, falling back to risk_based sizing.")
                return amount_to_risk / close_price
                
        else:
            self.log_message(f"Unknown position sizing method: {method}. Defaulting to risk_based sizing.")
            return amount_to_risk / close_price
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Send an event through the queue to be broadcast via WebSocket."""
        if hasattr(self, 'stream_publisher') and self.stream_publisher:
            try:
                self.stream_publisher(event_type, data)
            except Exception as e:
                logger.error(f"Error emitting event to stream: {e}")

        if self.event_queue:
            try:
                event = {
                    "type": event_type,
                    "data": data
                }
                self.log_message(f"Emitting event: {event}")
                self.event_queue.put(event)
            except Exception as e:
                logger.error(f"Error emitting event to queue: {e}")
    def _emit_trade_event(self, side: str, symbol: str, quantity: float, price: float):
        """Emit a simple trade event when a buy or sell occurs."""
        self.trade_counter += 1
        self._emit_event("trade", {
            "id": self.trade_counter,
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "price": price,
            "timestamp": datetime.now().timestamp() * 1000,
            "status": "FILLED"
        })
        self.log_message(f"Emitted trade event: {side} {quantity} {symbol} @ {price}")
    
    def _emit_completed_trade(self, trade):
        """Emit a completed trade with full entry/exit details and P&L."""
        self.trade_counter += 1

        # NOTE: persistence.save_trade is deprecated in favor of full session sync.
        # However, we still might want to ensure the latest state is synced.
        # Ideally, _emit_position_update (which calls sync_portfolio_to_db) 
        # is called right after this in the main loop anyway.
        
        self._emit_event("completed_trade", {
            "id": self.trade_counter,
            "symbol": trade.symbol,
            "side": "SELL",  # Completed trades are recorded on exit
            "quantity": trade.quantity,
            "entryPrice": trade.entry_price,
            "exitPrice": trade.exit_price,
            "entryTime": trade.entry_time.timestamp() * 1000 if hasattr(trade.entry_time, 'timestamp') else datetime.now().timestamp() * 1000,
            "exitTime": trade.exit_time.timestamp() * 1000 if hasattr(trade.exit_time, 'timestamp') else datetime.now().timestamp() * 1000,
            "pnl": trade.pnl,
            "status": "CLOSED"
        })
        self.log_message(f"Emitted completed trade event: {trade.symbol} | P&L: ${trade.pnl:.2f}")
    def _emit_position_update(self):
        """Emit current positions and account info."""
        
        # Sync full portfolio state to DB
        if self.persistence:
             self.persistence.sync_portfolio_to_db(self.portfolio)

        positions_data = []
        for symbol, lots in self.portfolio.positions.items():
            total_qty = sum(lot.quantity for lot in lots)
            avg_price = sum(lot.entry_price * lot.quantity for lot in lots) / total_qty if total_qty > 0 else 0
            positions_data.append({
                "symbol": symbol,
                "quantity": total_qty,
                "avgPrice": avg_price
            })
        
        self._emit_event("position", {
            "cash": self.portfolio.cash,
            "positions": positions_data,
            "accountValue": self.get_portfolio_value(),
            "timestamp": datetime.now().timestamp() * 1000
        })
    
    def _emit_metrics_update(self):
        """Emit performance metrics."""
        total_pnl = sum(trade.pnl for trade in self.portfolio.trades)
        winning_trades = [t for t in self.portfolio.trades if t.pnl > 0]
        losing_trades = [t for t in self.portfolio.trades if t.pnl < 0]
        win_rate = (len(winning_trades) / len(self.portfolio.trades) * 100) if self.portfolio.trades else 0
        
        self._emit_event("metrics", {
            "totalPnL": total_pnl,
            "totalTrades": len(self.portfolio.trades),
            "winRate": win_rate,
            "winningTrades": len(winning_trades),
            "losingTrades": len(losing_trades),
            "accountValue": self.get_portfolio_value(),
            "timestamp": datetime.now().timestamp() * 1000
        })