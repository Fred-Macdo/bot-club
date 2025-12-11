from lumibot.strategies import Strategy
from lumibot.entities import Asset, Position
from lumibot.backtesting import YahooDataBacktesting
from lumibot.brokers import Alpaca

from datetime import datetime
import pandas as pd
from typing import Dict, Union, List, Any
import numpy as np
import polars as pl
import logging
import asyncio
import threading
from ..indicators.indicator_factory import IndicatorFactory
from ..utils.condition_checker import ConditionChecker
from ..utils.indicator_converter import IndicatorConverter
from ..utils.trade_logger import TradeLogger
from ..utils.websocket_manager import WebSocketLogHandler
from alpaca.trading.client import TradingClient
from ..utils.portfolio_manager import Portfolio, Position, Trade
from .strategy_persistence import StrategyPersistence
import json

logger = logging.getLogger(__name__)

# Set consistent formatting options at the beginning of the script
pd.set_option('display.precision', 2)
np.set_printoptions(precision=2, suppress=True)  # Added suppress=True to avoid scientific notation

class StockStrategy(Strategy):
    """
    This class is adapted for stock trading. It takes a yaml configuration file 
    as a strategy and runs it using Lumibot lifecycle methods.
    """
    def initialize(self,
                   strategy_config: Dict[str, Any],
                   event_queue=None,
                   strategy_id=None, 
                   db=None,
                   user_id=None):
        
        self.indicator_converter = IndicatorConverter()
        self.strategy = strategy_config.get("config")
        self.symbols = self.strategy.get('symbols', [])
        self.timeframe = self.strategy.get('timeframe', '1Day') # Default timeframe for stocks
        self.sleeptime = '1M' # Check less frequently for stocks
        self.params = self.indicator_converter.convert_indicators_to_params(self.strategy.get('indicators', []))
        self.entry_conditions = self.strategy.get('entry_conditions', [])
        self.exit_conditions = self.strategy.get('exit_conditions', [])
        self.risk_management = self.strategy.get('risk_management', {})
        self.set_market("NYSE") # Set to standard stock market hours
        self.portfolio = Portfolio()
        self.portfolio.set_initial_capital(self.get_cash())
        self.condition_checker = ConditionChecker()
        self.persistence = StrategyPersistence(db=db, 
                                               strategy_id=strategy_id, 
                                               user_id=user_id)

        # Store event queue and strategy_id for emitting events
        self.event_queue = event_queue
        self.strategy_id = strategy_id
        self.trade_counter = 0
    
    def _save_position_to_db(self, position: Position):
        """Save a position to MongoDB."""
        if self.persistence:
            try:
                self.persistence.save_position(position)
                logger.debug(f"Position saved to DB: {position.symbol}")
            except Exception as e:
                logger.error(f"Error saving position to DB: {e}")
    
    def _save_trade_to_db(self, trade: Trade):
        """Save a trade to MongoDB."""
        if self.persistence:
            try:
                self.persistence.save_trade(trade)
                logger.info(f"Trade saved to DB: {trade.symbol} P&L={trade.pnl:.2f}")
            except Exception as e:
                logger.error(f"Error saving trade to DB: {e}")
    
    def _delete_position_from_db(self, position_id: str):
        """Delete a position from MongoDB when fully closed."""
        if self.persistence:
            try:
                self.persistence.delete_position(position_id)
                logger.debug(f"Position deleted from DB: {position_id}")
            except Exception as e:
                logger.error(f"Error deleting position from DB: {e}")
        

    def on_trading_iteration(self):
        self.log_message(f"Strategy: {self.strategy}")
        self.log_message(f"Symbols: {self.symbols}")
        # ... (rest of the initial logging is the same) ...

        # Get the cash balance, positions, and portfolio value
        cash = self.get_cash()
        positions = self.get_positions()
        self.log_message(f"Date: {self.get_datetime()}")
        self.log_message(f"Cash Balance: {cash:.2f}")
        self.log_message(f"Current Positions: {positions}")
        self.log_message(f"Account Value: {self.get_portfolio_value():.2f}")

        # 1. Get the assets
        self.log_message("Getting assets")
        # Define assets as stocks
        assets = [Asset(x, asset_type=Asset.AssetType.STOCK) for x in self.symbols]
        for asset in assets: 
            # 3. Get data for each symbol
            prices = self.get_historical_prices(asset, 50, self.timeframe)
           
            if prices is None or prices.df.empty:
                self.log_message(f"Could not retrieve price data for {asset.symbol}")
                continue

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
                
                # Logging remains the same...
                n_rows = 2
                df_to_log = (
                    df.tail(n_rows)
                      .with_columns(pl.col(pl.Float64).round(4))
                      .to_pandas()
                )
                indicator_table = df_to_log.to_string(index=False)
                self.log_message(
                    f"Technical indicators (last {n_rows} rows):\n" + indicator_table
                )
                
                # JSON payload for frontend...
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
                    # Create and submit the sell order (no quote asset needed for stocks)
                    order = self.create_order(
                        asset=asset,
                        quantity=position.quantity,
                        side="sell"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    
                    # Update portfolio and emit events
                    completed_trades = self.portfolio.sell(asset.symbol, position.quantity, latest_data['close'], self.get_datetime())
                    for trade in completed_trades:
                        self._emit_completed_trade(trade)
                        # Save each completed trade to MongoDB
                        self._save_trade_to_db(trade)
                    
                    # Delete closed positions from DB (if fully closed)
                    if asset.symbol not in self.portfolio.positions:
                        # All positions for this symbol were closed
                        for trade in completed_trades:
                            self._delete_position_from_db(trade.position_id)
                    
                    self._emit_trade_event("sell", asset.symbol, position.quantity, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()

                # 9. If we have a position, check if DCA entry conditions are met
                elif entry_conditions:
                    self.log_message(f"DCA Entry conditions met for {asset.symbol}: {entry_data_context}")  
                    position_size = self._calculate_position_size(asset, latest_data)
                    
                    # Create and submit the buy order
                    order = self.create_order(
                        asset=asset,
                        quantity=position_size,
                        side="buy"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    
                    # Update portfolio and emit events
                    new_position = self.portfolio.add_buy(asset.symbol, position_size, latest_data['close'], self.get_datetime())
                    
                    # Save new position to MongoDB
                    if new_position:
                        self._save_position_to_db(new_position)
                    
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()

            else:
                # 10. If we don't have a position, check entry conditions
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")
                    position_size = self._calculate_position_size(asset, latest_data)
                    
                    # Create and submit the buy order (no quote asset needed for stocks)
                    order = self.create_order(
                        asset=asset,
                        quantity=position_size,
                        side="buy"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)

                    # Update portfolio and emit events
                    new_position = self.portfolio.add_buy(asset.symbol, position_size, latest_data['close'], self.get_datetime())
                    
                    # Save new position to MongoDB
                    if new_position:
                        self._save_position_to_db(new_position)
                    
                    self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df['close'][-1]:.2f}")
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()

        self.log_message("**********************************************************************************")

    # All helper functions (_check_entry_conditions, _check_exit_conditions, 
    # _calculate_position_size, _emit_event, etc.) can be copied directly 
    # from CryptoStrategy without changes, so they are omitted here for brevity.
    # You should include them in your actual class definition.
    
    def on_abrupt_closing(self):
        self.sell_all()

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
        if self.event_queue:
            try:
                event = {
                    "type": event_type,
                    "data": data
                }
                self.event_queue.put(event)
            except Exception as e:
                self.log_message(f"Error emitting event: {e}")
    
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
    
    def _emit_completed_trade(self, trade):
        """Emit a completed trade with full entry/exit details and P&L."""
        self.trade_counter += 1
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
    
    def _emit_position_update(self):
        """Emit current positions and account info."""
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
                   user_id=None):
        
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
        self.strategy_id = strategy_id
        self.db = db
        self.user_id = user_id
        self.trade_counter = 0
    
    def _save_position_to_db(self, position: Position):
        """Save a position to MongoDB."""
        if self.persistence:
            try:
                self.persistence.save_position(position)
                logger.debug(f"Position saved to DB: {position.symbol}")
            except Exception as e:
                logger.error(f"Error saving position to DB: {e}")
    
    def _save_trade_to_db(self, trade: Trade):
        """Save a trade to MongoDB."""
        if self.persistence:
            try:
                self.persistence.save_trade(trade)
                logger.info(f"Trade saved to DB: {trade.symbol} P&L={trade.pnl:.2f}")
            except Exception as e:
                logger.error(f"Error saving trade to DB: {e}")
    
    def _delete_position_from_db(self, position_id: str):
        """Delete a position from MongoDB when fully closed."""
        if self.persistence:
            try:
                self.persistence.delete_position(position_id)
                logger.debug(f"Position deleted from DB: {position_id}")
            except Exception as e:
                logger.error(f"Error deleting position from DB: {e}")

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
                        # Save each completed trade to MongoDB
                        self._save_trade_to_db(trade)
                    
                    # Delete closed positions from DB (if fully closed)
                    if asset.symbol not in self.portfolio.positions:
                        # All positions for this symbol were closed
                        for trade in completed_trades:
                            self._delete_position_from_db(trade.position_id)
                    
                    # Also emit simple transaction event for real-time feedback
                    self._emit_trade_event("sell", asset.symbol, position.quantity, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()
                
                # 9. if we have a position, check if the DCA entry conditions are met, 
                #    if so; buy the asset
                
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")  
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
                    
                    # Save new position to MongoDB
                    if new_position:
                        self._save_position_to_db(new_position)
                    
                    # Emit trade and position events
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()
            # 10. If we don't have a position, check if the entry conditions are met, if so; buy the asset
            else:
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")
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
                    
                    # Save new position to MongoDB
                    if new_position:
                        self._save_position_to_db(new_position)
                    
                    self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df['close'][-1]:.2f}")
                    
                    # Emit trade and position events
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])
                    self._emit_position_update()
                    self._emit_metrics_update()
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
        if self.event_queue:
            try:
                event = {
                    "type": event_type,
                    "data": data
                }
                self.event_queue.put(event)
            except Exception as e:
                self.log_message(f"Error emitting event: {e}")
    
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
    
    def _emit_completed_trade(self, trade):
        """Emit a completed trade with full entry/exit details and P&L."""
        self.trade_counter += 1
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
    
    def _emit_position_update(self):
        """Emit current positions and account info."""
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