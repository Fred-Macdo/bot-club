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

from ...utils.indicator_factory import IndicatorFactory
from ...utils.condition_checker import ConditionChecker
from ...utils.indicator_converter import IndicatorConverter
from ...utils.trade_logger import TradeLogger
from ...utils.enums import LogEventType
from ...models.portfolio_models import *
from decimal import Decimal
import json
logger = logging.getLogger(__name__)
from ...utils.portfolio_persistence import PortfolioPersistence

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
                   user_id=None,
                   stream_publisher=None,
                   initial_capital=100000.0):
        
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
        account_value = self.get_cash()
        effective_capital = max(float(initial_capital), float(account_value))
        logger.info(f"Initial capital: user_defined={initial_capital}, account_value={account_value}, effective={effective_capital}")
        self.portfolio = StrategyPortfolio(strategy_id=strategy_config.get("_id"),
                                           strategy_name=strategy_config.get("name", "Unnamed Strategy"),
                                           user_id=strategy_config.get("user_id"),
                                           initial_capital=effective_capital,
                                           current_cash=account_value,
                                           performance=PerformanceMetrics())
        self.condition_checker = ConditionChecker()

        # Store event queue and strategy_id for emitting events
        self.event_queue = event_queue
        self.stream_publisher = stream_publisher
        self.strategy_id = strategy_id
        self.db = db
        self.user_id = user_id
        self.trade_counter = 0
        
        # Initialize persistence layer
        self.persistence = PortfolioPersistence(
            db=db,
            stream_publisher=stream_publisher,
            strategy_id=strategy_id,
            user_id=user_id
        )
    
    def log_message(self, message, level='info', color=None, broadcast=True, event_type=LogEventType.LOG):
        # Lumibot's Strategy.log_message does not accept 'broadcast'
        super().log_message(message, level, color)
        
        if hasattr(self, 'stream_publisher') and self.stream_publisher and broadcast:
             payload = {
                "event_type": event_type,
                "timestamp": datetime.now().timestamp() * 1000, 
                "level": str(level).upper(), 
                "message": str(message)
             }
             
             # Attempt to parse message if it looks like a JSON object (for rich data)
             if isinstance(message, str) and message.strip().startswith('{'):
                 try:
                     data = json.loads(message)
                     if isinstance(data, dict):
                         payload['data'] = data
                         if 'title' in data:
                             payload['message'] = data['title']
                 except:
                     pass

             self.stream_publisher("log", payload)

    def on_trading_iteration(self):
        self.log_message(f"Strategy: {self.strategy}")
        self.log_message(f"Symbols: {self.symbols}")

        cash = self.get_cash()
        positions = self.get_positions()
        self.log_message(f"Date: {self.get_datetime()}")
        self.log_message(f"Cash Balance: {cash:.2f}")

        # Send structured positions data for frontend components
        positions_data = []
        for pos in positions:
            pos_data = {
                "symbol": pos.asset.symbol if hasattr(pos, 'asset') and hasattr(pos.asset, 'symbol') else str(pos),
                "quantity": float(pos.quantity) if hasattr(pos, 'quantity') else 0,
            }
            positions_data.append(pos_data)
        self.log_message(
            json.dumps({"title": f"Current Positions ({len(positions)} open)", "positions": positions_data}),
            event_type=LogEventType.POSITIONS
        )

        # Send structured account value data for frontend components
        acct_value = self.get_portfolio_value()
        self.log_message(
            json.dumps({"title": f"Account Value: ${acct_value:.2f}", "account_value": float(acct_value), "cash": float(cash)}),
            event_type=LogEventType.ACCOUNT_VALUE
        )

        # Track latest prices for all assets
        latest_prices = {}
        
        assets = [Asset(x, asset_type=Asset.AssetType.STOCK) for x in self.symbols]
        for asset in assets: 
            prices = self.get_historical_prices(asset, 50, self.timeframe)
           
            if prices is None or prices.df.empty:
                self.log_message(f"Could not retrieve price data for {asset.symbol}")
                continue

            prices.df["symbol"] = asset.symbol
            position = self.get_position(asset)
            prices_df = pl.from_pandas(prices.df)
            
            technicals = IndicatorFactory(prices_df, self.params)
            df = technicals.calculate_indicators()

            if df is None or df.is_empty():
                self.log_message(f"No indicators calculated for {asset.symbol}")
                continue
            else:
                self.log_message(f"Indicators calculated for {asset.symbol}")
                
                n_rows = 2
                df_to_log = (
                    df.tail(n_rows)
                      .with_columns(pl.col(pl.Float64).round(4))
                      .to_pandas()
                )
                
                df_json_string = df_to_log.to_json(orient="records")
                df_data = json.loads(df_json_string)
                log_payload = {
                    "type": "dataframe",
                    "title": f"Technical Indicators for {asset.symbol}",
                    "data": df_data
                }
                self.log_message(json.dumps(log_payload, indent=4))

                latest_data = df.row(-1, named=True)
                latest_prices[asset.symbol] = latest_data['close']  # Store for portfolio update
                entry_conditions, entry_data_context = self._check_entry_conditions(latest_data)

            self.log_message(f"Position: {position}, type: {type(position)}")
            if position:
                exit_conditions, exit_reason, exit_data_context = self._check_exit_conditions(latest_data, asset)
                if exit_conditions:
                    self.log_message(f"Exit conditions met for {asset.symbol}: {exit_reason}")
                    order = self.create_order(
                        asset=asset,
                        quantity=position.quantity,
                        side="sell"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    
                    completed_trades = self.portfolio.process_sell(
                        symbol=asset.symbol,
                        quantity=position.quantity,
                        exit_price=latest_data['close'],
                        exit_time=self.get_datetime(),
                        exit_reason=exit_reason
                    )
                    
                    self.portfolio.update_performance_metrics()

                    # Persist completed trades
                    for trade in completed_trades:
                        self.persistence.save_completed_trade(trade)
                    
                    self._emit_trade_event("sell", asset.symbol, position.quantity, latest_data['close'])

                elif entry_conditions:
                    self.log_message(f"DCA Entry conditions met for {asset.symbol}: {entry_data_context}")  
                    position_size = self._calculate_position_size(asset, latest_data)
                    
                    order = self.create_order(
                        asset=asset,
                        quantity=position_size,
                        side="buy"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)
                    
                    new_lot = PositionLot(
                        symbol=asset.symbol,
                        quantity=Decimal(str(position_size)),
                        entry_price=Decimal(str(latest_data['close'])),
                        entry_time=self.get_datetime(),
                        entry_reason=str(entry_data_context),
                        strategy_id=self.portfolio.strategy_id,
                        user_id=self.portfolio.user_id,
                        alpaca_order_id=str(order.id)
                    )
                    self.portfolio.add_buy(new_lot)
                    
                    # Persist buy
                    self.persistence.save_buy(new_lot)
                    
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])

            else:
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")
                    position_size = self._calculate_position_size(asset, latest_data)
                    
                    order = self.create_order(
                        asset=asset,
                        quantity=position_size,
                        side="buy"
                    )
                    self.submit_order(order)
                    self.wait_for_order_execution(order)

                    new_lot = PositionLot(
                        symbol=asset.symbol,
                        quantity=Decimal(str(position_size)),
                        entry_price=Decimal(str(latest_data['close'])),
                        entry_time=self.get_datetime(),
                        entry_reason=str(entry_data_context),
                        strategy_id=self.portfolio.strategy_id,
                        user_id=self.portfolio.user_id,
                        alpaca_order_id=str(order.id)
                    )
                    self.portfolio.add_buy(new_lot)
                    
                    # Persist buy
                    self.persistence.save_buy(new_lot)
                    
                    self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df['close'][-1]:.2f}")
                    self._emit_trade_event("buy", asset.symbol, position_size, latest_data['close'])

        # End of iteration - save portfolio snapshot
        self.log_message("Saving portfolio snapshot to DB")
        self.portfolio.update_performance_metrics()
        
        snapshot_data = self.portfolio.model_dump()
        snapshot_data['user_id'] = str(snapshot_data['user_id'])
        snapshot_data['strategy_id'] = str(snapshot_data['strategy_id'])
        self.log_message(
            self.portfolio.model_dump_json(indent=4, exclude={'user_id', 'strategy_id'}),
            event_type=LogEventType.PORTFOLIO_SNAPSHOT
        )
        
        # Persist portfolio snapshot
        self.persistence.save_portfolio_snapshot(self.portfolio, latest_prices)
        self.persistence.sync_portfolio_to_db(self.portfolio)

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
                                                       row=row)
    
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
            "quantity": float(trade.quantity),
            "entryPrice": float(trade.entry_price),
            "exitPrice": float(trade.exit_price),
            "entryTime": trade.entry_time.timestamp() * 1000 if hasattr(trade.entry_time, 'timestamp') else datetime.now().timestamp() * 1000,
            "exitTime": trade.exit_time.timestamp() * 1000 if hasattr(trade.exit_time, 'timestamp') else datetime.now().timestamp() * 1000,
            "pnl": float(trade.realized_pnl),
            "status": "CLOSED"
        })
    
    def _emit_position_update(self):
        """Emit current positions and account info."""
        
        # Sync full portfolio state to DB
        # if self.persistence:
        #      self.persistence.sync_portfolio_to_db(self.portfolio)

        positions_data = []
        for symbol, lots in self.portfolio.lots.items():
            total_qty = sum(lot.quantity for lot in lots)
            if total_qty > 0:
                cost_basis = sum(lot.cost_basis for lot in lots)
                avg_price = cost_basis / total_qty
                positions_data.append({
                    "symbol": symbol,
                    "quantity": float(total_qty),
                    "avgPrice": float(avg_price)
                })
        
        self._emit_event("position", {
            "cash": float(self.portfolio.current_cash),
            "positions": positions_data,
            "accountValue": float(self.portfolio.current_cash) + sum([p["quantity"] * p["avgPrice"] for p in positions_data]),
            "timestamp": datetime.now().timestamp() * 1000
        })
    
    def _emit_metrics_update(self):
        """Emit performance metrics."""
        perf = self.portfolio.performance

        self._emit_event("metrics", {
            "totalPnL": float(perf.total_pnl),
            "totalTrades": perf.total_trades,
            "winRate": perf.win_rate,
            "winningTrades": perf.winning_trades,
            "losingTrades": perf.losing_trades,
            "accountValue": float(self.portfolio.current_cash),
            "timestamp": datetime.now().timestamp() * 1000
        })