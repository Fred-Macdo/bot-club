import asyncio
import logging
from math import log
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import polars as pl
from pymongo.database import Database

from ..data_retrieval.data_manager import DataManager, TIMEFRAME_MAPPINGS
from ..indicators.indicator_factory import IndicatorFactory
from ...models.portfolio_models import StrategyPortfolio
from ..utils.condition_checker import ConditionChecker
from ..utils.enums import TradingMode
from ..utils.indicator_converter import IndicatorConverter
from ..utils.trade_logger import TradeLogger
from ..utils.websocket_manager import WebSocketLogHandler
from alpaca.trading.client import TradeClient
logger = logging.getLogger(__name__)



class LiveStrategyExecutor:
    """Handles live strategy execution logic."""

    def __init__(
        self,
        db: Database,
        user_id: str,
        mode: TradingMode,
        strategy: Dict[str, Any],
        strategy_id: str,
        data_provider: str
    ):
        self.db = db
        self.user_id = user_id
        self.mode = mode
        self.strategy_id = strategy_id
        self.strategy = strategy
        self.data_provider = data_provider
        self.condition_checker = ConditionChecker()
        self.indicator_converter = IndicatorConverter()
        self.trade_logger = TradeLogger()
        self.is_running = False
        self._stop_event = asyncio.Event()

        # Add the WebSocket handler to the logger
        self.logger = logging.getLogger(f"{__name__}.{strategy_id}")
        self.logger.addHandler(WebSocketLogHandler(strategy_id=self.strategy_id))
        self.logger.setLevel(logging.INFO)


    async def start(self):
        """Starts the live strategy execution loop."""
        self.alpaca_client = await self._get_portfolio_manager()
        self.is_running = True
        self._stop_event.clear()
        config = self.strategy.get("strategy_config") or self.strategy.get("yaml_config") or self.strategy.get("config")
        logger.info(f"Live strategy configuration: {config}")
        if not config:
            raise ValueError("No strategy configuration found")

        symbols = config.get("symbols", [])
        timeframe = config.get("timeframe", "15Min")  # Default to 15 minutes
        
        data_manager = DataManager(self.db)
        logger.info(f"Data manager initialized: {data_manager.data_provider}")
        # Initialize the data provider - THIS WAS MISSING!
        await data_manager.initialize_provider(self.data_provider, self.user_id)

        logger.info(f"Data manager initialized: {data_manager}")
        while not self._stop_event.is_set():
            try:
                self.logger.info("Fetching new market data...")
                
                # We need enough data to calculate indicators, so we fetch a range.
                # A lookback of 100 periods should be sufficient for most indicators.
                market_data = await data_manager.fetch_data(symbols,
                                                            timeframe,
                                                            limit=25, 
                                                            data_provider=self.data_provider)
                
                self.logger.info(f"Market data fetched: {market_data}")
                if market_data.is_empty():
                    self.logger.warning("No market data fetched. Waiting for next interval.")
                    await asyncio.sleep(self._get_sleep_duration(timeframe))
                    continue

                await self._process_market_data(market_data, config, symbols)

                await asyncio.sleep(self._get_sleep_duration(timeframe))

            except Exception as e:
                self.logger.error(f"An error occurred in the trading loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    async def stop(self):
        """Stops the live strategy execution loop."""
        self.is_running = False
        self._stop_event.set()
        self.logger.info("Live strategy executor stopping...")

    def _get_sleep_duration(self, timeframe: str) -> int:
        """Determines sleep duration in seconds based on timeframe."""
        if "Min" in timeframe:
            return int(timeframe.replace("Min", "")) * 60
        elif "Hour" in timeframe:
            return int(timeframe.replace("Hour", "")) * 3600
        elif "Day" in timeframe:
            return int(timeframe.replace("Day", "")) * 86400
        return 10  # Default to 1 minute for unknown timeframes

    async def _process_market_data(self, data: pl.DataFrame, config: Dict, symbols: List[str]):
        """Processes fetched market data to check for trading signals."""
        self.logger.info("Processing market data for signals...")
        indicator_params = self.indicator_converter.convert_indicators_to_params(config.get("indicators", []))
        risk_management = config.get("risk_management", {})
        
        for symbol in symbols:
            symbol_df = data.filter(pl.col("symbol") == symbol)
            if symbol_df.is_empty():
                continue

            indicator_factory = IndicatorFactory(symbol_df, indicator_params)
            symbol_df_with_indicators = indicator_factory.get_indicators()

            if symbol_df_with_indicators is None or symbol_df_with_indicators.is_empty():
                continue

            latest_data = symbol_df_with_indicators.row(-1, named=True)

            await self._check_exit_conditions(symbol, latest_data, config.get("exit_conditions", []))
            
            await self._check_entry_conditions(symbol, 
                                               latest_data, 
                                               config.get("entry_conditions", []), 
                                               risk_management, 
                                               config)

    async def _check_exit_conditions(self, symbol: str, latest_data: Dict, exit_conditions: List):
        """Checks and executes exit conditions for a symbol."""
        position = self.portfolio_manager.get_position(symbol)
        if not position:
            return

        should_exit, reason, _ = self.condition_checker.check_exit_conditions(
            conditions=exit_conditions,
            row=latest_data,
            position=position,
            current_time=latest_data['datetime']
        )
        if should_exit:
            self.logger.info(f"Exit signal for {symbol}: {reason}")

            last_trade = await self.db['trades'].find_one(
                {"user_id": self.user_id, "symbol": symbol, "mode": self.mode.value},
                sort=[("exit_time", -1)]
            )
            last_exit_time = last_trade['exit_time'] if last_trade else datetime.min.replace(tzinfo=timezone.utc)

            first_entry_signal = await self.db['entry_signals'].find_one({
                "user_id": self.user_id,
                "symbol": symbol,
                "mode": self.mode.value,
                "timestamp": {"$gt": last_exit_time}
            }, sort=[("timestamp", 1)])

            entry_time = first_entry_signal['timestamp'] if first_entry_signal else latest_data['datetime']
            
            await self.portfolio_manager.close_position(symbol)

            self.trade_logger.log_trade(
                symbol=symbol,
                entry_time=entry_time,
                exit_time=latest_data['datetime'],
                entry_price=position.cost_basis / position.qty,
                exit_price=Decimal(str(latest_data['close'])),
                quantity=position.qty,
                pnl=position.unrealized_pl,
                trade_type='buy',
                strategy_name=self.strategy.get('name', 'Unknown Strategy'),
                exit_reason=reason
            )

    async def _check_entry_conditions(self, symbol: str, latest_data: Dict, entry_conditions: List, risk_management: Dict, config: Dict):
        """Checks and executes entry conditions for a symbol."""
        dca_config = config.get('dollar_cost_averaging', {})
        dca_enabled = dca_config.get('enabled', False)
        max_positions = dca_config.get('max_positions', 1)

        position = self.portfolio_manager.get_position(symbol)
        if position:
            if not dca_enabled:
                return

            last_trade = await self.db['trades'].find_one(
                {"user_id": self.user_id, "symbol": symbol, "mode": self.mode.value},
                sort=[("exit_time", -1)]
            )
            last_exit_time = last_trade['exit_time'] if last_trade else datetime.min.replace(tzinfo=timezone.utc)
            
            current_entry_count = await self.db['entry_signals'].count_documents({
                "user_id": self.user_id,
                "symbol": symbol,
                "mode": self.mode.value,
                "timestamp": {"$gt": last_exit_time}
            })
            logger.info(f"LIVE STRATEGY EXECUTOR: Current entry count for {symbol}: {current_entry_count}")
            logger.info(f"LIVE STRATEGY EXECUTOR: Max positions : {max_positions}")
            if current_entry_count >= max_positions:
                self.logger.info(f"DCA max positions ({max_positions}) reached for {symbol}. No new entry.")
                return

        should_enter, reason, _ = self.condition_checker.check_entry_conditions(
            conditions=entry_conditions, 
            row=latest_data
        )
        if should_enter:
            self.logger.info(f"Entry signal for {symbol}: {reason}")

            position_sizing_method = risk_management.get("position_sizing_method", "fixed")
            risk_per_trade = risk_management.get("risk_per_trade")
            stop_loss = risk_management.get("stop_loss")
            take_profit = risk_management.get("take_profit")
            
            current_price = Decimal(str(latest_data['close']))
            quantity = Decimal('0')

            if position_sizing_method == "risk_based" and risk_per_trade and stop_loss:
                try:
                    account = self.portfolio_manager.get_account()
                    portfolio_value = account.portfolio_value
                    risk_amount = portfolio_value * Decimal(str(risk_per_trade))
                    risk_per_share = current_price * Decimal(str(stop_loss))
                    if risk_per_share > 0:
                        quantity = risk_amount / risk_per_share
                except Exception as e:
                    self.logger.error(f"Error calculating position size: {e}")
                    return
            else:
                self.logger.warning("Position sizing method not supported or configured properly. Cannot place trade.")
                return

            if quantity <= 0:
                self.logger.info(f"Calculated quantity for {symbol} is {quantity}. Skipping trade.")
                return

            stop_loss_price = current_price * (1 - Decimal(str(stop_loss))) if stop_loss else None
            take_profit_price = current_price * (1 + Decimal(str(take_profit))) if take_profit else None

            try:
                order = self.portfolio_manager.submit_order(
                    symbol=symbol,
                    qty=quantity.quantize(Decimal('0.0001')), # Adjust precision as needed
                    side='buy', # Assuming buy side for now
                    order_type='market',
                    time_in_force='gtc',
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price
                )
                self.logger.info(f"Submitted bracket order for {symbol}: {order}")
                # Log entry signal with trade details
                self.trade_logger.log_entry_signal(
                    symbol,
                    latest_data['datetime'],
                    current_price,
                    self.strategy.get('name', 'Unknown Strategy'),
                    [reason]
                )
            except Exception as e:
                self.logger.error(f"Failed to submit order for {symbol}: {e}", exc_info=True)

    async def _get_portfolio_manager(self):
        user_config = await self.db['user_config'].find_one({"user_id": self.user_id})
        if not user_config:
            raise ValueError("No user configuration found")
        
        if self.mode == TradingMode.PAPER:
            api_key = user_config.get('alpaca_paper_api_key')
            secret_key = user_config.get('alpaca_paper_secret_key')
        elif self.mode == TradingMode.LIVE:
            api_key = user_config.get('alpaca_live_api_key')
            secret_key = user_config.get('alpaca_live_secret_key')
        else:
            raise ValueError("Invalid trading mode")

        if api_key and secret_key:
            # Decrypt secret key if needed
            try:
                from models.user_config import ConfigEncryption
                decrypted_api_key = ConfigEncryption.decrypt_value(api_key)
                decrypted_secret = ConfigEncryption.decrypt_value(secret_key)
            except Exception as e:
                self.logger.warning(f"Could not decrypt secret key, using as-is: {e}")
                decrypted_secret = secret_key

        return TradeClient(api_key=decrypted_api_key, secret_key=decrypted_secret)