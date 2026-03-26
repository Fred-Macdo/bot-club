from lumibot.strategies import Strategy
from lumibot.entities import Asset, Position
from lumibot.backtesting import YahooDataBacktesting, AlpacaBacktesting, PolygonDataBacktesting
from lumibot.brokers import Alpaca
from bson import ObjectId
from decimal import Decimal
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, Union, List, Any
import numpy as np
import polars as pl
import logging
from ...utils.json_encoder import CustomJSONEncoder
from ...utils.portfolio_persistence import PortfolioPersistence

from ...utils.indicator_factory import IndicatorFactory
from ...utils.condition_checker import ConditionChecker
from ...utils.indicator_converter import convert_indicators_to_params
from ...utils.trade_logger import TradeLogger
from ...utils.enums import LogEventType
from ...models.portfolio_models import *
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
                   stream_publisher=None,
                   initial_capital=100000.0):
        
        
        self.strategy = strategy_config.get("config")
        self.symbols = self.strategy.get('symbols', [])
        self.timeframe = self.strategy.get('timeframe', '15M')
        self.sleeptime = '10S'
        self.params = convert_indicators_to_params(self.strategy.get('indicators', []))
        self.entry_conditions = self.strategy.get('entry_conditions', [])
        self.exit_conditions = self.strategy.get('exit_conditions', [])
        self.risk_management = self.strategy.get('risk_management', {})
        self.set_market("24/7")
        logger.info(f"Types for strategy config: symbols: {type(self.symbols)}, timeframe: {type(self.timeframe)}, params: {type(self.params)}, entry_conditions: {type(self.entry_conditions)}, exit_conditions: {type(self.exit_conditions)}, risk_management: {type(self.risk_management)}")
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
        self.dca_enabled = self.strategy.get('dca_enabled', False)
        
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
        # Fix: Do not pass 'broadcast' to the parent method
        super().log_message(message, level, color)
        
        if broadcast and hasattr(self, 'stream_publisher') and self.stream_publisher:
             payload = {
                 "event_type": event_type,
                "timestamp": datetime.now().timestamp() * 1000, 
                "level": str(level).upper(), 
                "message": str(message)
            }
             
             # Attempt to parse message if it looks like a JSON object (for rich data)
             if isinstance(message, str) and message.strip().startswith('{'):
                 try:
                     import json
                     data = json.loads(message)
                     if isinstance(data, dict):
                         payload['data'] = data
                         # If it's a data wrapping object, use title/description as the main message text
                         if 'title' in data:
                             payload['message'] = data['title']
                 except:
                     # Not valid JSON, ignore
                     pass

             self.stream_publisher("log", payload)

    def _emit_log(self, message, level="INFO"):
        self.log_message(message, level=level)
    
    def on_trading_iteration(self):


        # Get the cash balance, positions, and portfolio value
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

        #Lumibot Assets
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
                      )

                # Keep the JSON payload for the frontend to render as a table if needed
                df_json_string = df_to_log.write_json()
                df_data = json.loads(df_json_string)
                log_payload = {
                    "type": "dataframe",
                    "title": f"Technical Indicators for {asset.symbol}",
                    "data": df_data
                }
                self.log_message(json.dumps(log_payload, indent=4), event_type=LogEventType.PRICE_DATAFRAME)

                latest_data = df.row(-1, named=True)
                latest_prices[asset.symbol] = latest_data['close']  # Store for portfolio update
                entry_conditions, entry_data_context = self._check_entry_conditions(latest_data)
            self.log_message(f"Position: {position}, type: {type(position)}")
            if position:
                # 5. IF WE HAVE A POSITION, CHECK THE EXIT CONDITIONS
                exit_conditions, exit_reason, exit_data_context = self._check_exit_conditions(latest_data, asset)
                if exit_conditions:
                    self.log_message(f"Exit conditions met for {asset.symbol}: {exit_reason}", event_type=LogEventType.EXIT_CONDITIONS)
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
                    
                    completed_trades = self.portfolio.process_sell(
                        symbol=asset.symbol,
                        quantity=position.quantity,
                        exit_price=latest_data['close'],
                        exit_time=self.get_datetime(),
                        reason=exit_reason
                    )
                    
                    self.portfolio.update_performance_metrics()
                    
                    # Persist completed trades to MongoDB and Redis
                    for trade in completed_trades:
                        self.persistence.save_completed_trade(trade)
                        self._emit_log(f"📈 TRADE CLOSED: {trade.symbol} | P&L: ${trade.realized_pnl:.2f}")
                    
                    self._emit_trade_event("sell", asset.symbol, position.quantity, latest_data['close'])
                
                # 9. if we have a position, check if the DCA entry conditions are met
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")  
                    self._emit_log(f"🟢 ENTRY: {asset.symbol}")
                    self.log_message(f"Entry conditions: {entry_conditions}")
                    self.log_message(f"Entry data context: {entry_data_context}")
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
                    
                    new_lot = PositionLot(
                        symbol=asset.symbol,
                        quantity=Decimal(str(position_size)),
                        entry_price=Decimal(str(latest_data['close'])),
                        entry_time=self.get_datetime(),
                        entry_reason=str(entry_data_context),
                        strategy_id=str(self.portfolio.strategy_id),
                        user_id=str(self.portfolio.user_id)
                    )
                    self.portfolio.add_buy(new_lot)
                    
                    # Persist buy to MongoDB and Redis
                    self.persistence.save_buy(new_lot)
                    self._emit_log(f"✅ BUY: {new_lot.quantity} {new_lot.symbol} @ ${new_lot.entry_price:.2f}")

            # 10. If we don't have a position, check if the entry conditions are met
            else:
                if entry_conditions:
                    self.log_message(f"Entry conditions met for {asset.symbol}: {entry_data_context}")
                    self._emit_log(f"🟢 ENTRY: {asset.symbol} conditions met")
                    self.log_message(f"Entry conditions: {entry_conditions}")
                    self.log_message(f"Entry data context: {entry_data_context}")
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
                    
                    # Persist buy to MongoDB and Redis
                    self.persistence.save_buy(new_lot)

                    self.log_message(f"New Position: {new_lot}")
                    self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df['close'][-1]:.2f}")
                    self._emit_log(f"✅ BUY: {position_size} {asset.symbol} @ ${latest_data['close']:.2f}")

        # End of trading iteration - save portfolio snapshot
        self.log_message("Saving portfolio snapshot to DB")
        self.portfolio.update_performance_metrics()
        
        snapshot_data = self.portfolio.model_dump()
        snapshot_data['user_id'] = str(snapshot_data['user_id'])
        snapshot_data['strategy_id'] = str(snapshot_data['strategy_id'])
        self.log_message(
            self.portfolio.model_dump_json(indent=4, exclude={'user_id', 'strategy_id'}),
            event_type=LogEventType.PORTFOLIO_SNAPSHOT
        )
        
        # Persist portfolio snapshot to MongoDB and publish full update to Redis
        self.persistence.save_portfolio_snapshot(self.portfolio, latest_prices)
        
        # Also sync full portfolio state for recovery purposes
        self.persistence.sync_portfolio_to_db(self.portfolio)

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

    def _get_positions_value(self, latest_prices: Dict[str, float]) -> Decimal:
        """Calculate total value of all positions based on latest prices"""
        if len(self.portfolio.lots) == 0:
            return Decimal(0)
        
        positions_value = Decimal(0)
        for symbol, lots in self.portfolio.lots.items():
            price = latest_prices.get(symbol)
            if price is not None:
                for lot in lots:
                    positions_value += Decimal(lot.quantity) * Decimal(price)
        return positions_value
    
    def _get_unrealized_pnl(self, latest_prices: Dict[str, float]) -> Decimal:
        """Calculate total unrealized P&L based on latest prices"""
        unrealized_pnl = Decimal(0)
        for symbol, lots in self.portfolio.lots.items():
            price = latest_prices.get(symbol)
            if price is not None:
                for lot in lots:
                    unrealized_pnl += (Decimal(price) - lot.entry_price) * lot.quantity
        return unrealized_pnl

    def _update_portfolio_snapshot(self, latest_prices: Dict[str, float]) -> PortfolioSnapshot:
        """Update portfolio snapshot"""
        timestamp = datetime.now(tz=timezone.utc)
        cash = Decimal(self.get_cash())
        positions_value = self._get_positions_value(latest_prices)
        total_value = cash + positions_value
        unrealized_pnl = self._get_unrealized_pnl(latest_prices)
        #realized_pnl = self.portfolio.performance.realized_pnl

        values = {
            "user_id": self.portfolio.user_id,
            "strategy_id": self.portfolio.strategy_id,
            "timestamp": timestamp,
            "cash": cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "unrealized_pnl": unrealized_pnl
        }

        return PortfolioSnapshot(**values)

    def _emit_portfolio_update(self, latest_prices: Dict[str, float]):
        """Emit portfolio update event - now handled by persistence layer"""
        self.persistence.save_portfolio_snapshot(self.portfolio, latest_prices)
