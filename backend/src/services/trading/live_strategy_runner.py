"""
LiveStrategyRunner
Replaces Lumibot-based CryptoStrategy/StockStrategy with a unified runner
that uses the same StrategyExecutor patterns (indicators, conditions) but
executes against the live Alpaca API via AlpacaTradingClient.

Key design principles:
1. Portfolio state is loaded from MongoDB session on start (resume support)
2. Portfolio state is saved after every iteration (crash recovery)
3. Uses strategy's own StrategyPortfolio for tracking — never resets to 0
4. Runs as a blocking loop inside a Celery task
5. Publishes all events to Redis stream for WebSocket delivery
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Callable

import polars as pl
from pymongo.database import Database

from .alpaca_client import AlpacaTradingClient
from ...services.data_retrieval.data_providers import AlpacaProvider, AVAILABLE_CRYPTO_ASSETS
from ...utils.indicator_factory import IndicatorFactory
from ...utils.condition_checker import ConditionChecker
from ...utils.indicator_converter import convert_indicators_to_params
from ...utils.trade_logger import TradeLogger
from ...utils.enums import LogEventType
from ...utils.portfolio_persistence import PortfolioPersistence
from ...models.portfolio_models import (
    StrategyPortfolio,
    PositionLot,
    PerformanceMetrics,
)

logger = logging.getLogger(__name__)


class LiveStrategyRunner:
    """
    Unified live/paper strategy runner.
    Fetches data, calculates indicators, checks conditions, and executes
    orders via the Alpaca REST API.  Maintains portfolio state in MongoDB.
    """

    # ==================== INITIALIZATION ====================

    def __init__(
        self,
        *,
        alpaca_client: AlpacaTradingClient,
        data_provider: AlpacaProvider,
        strategy_config: Dict[str, Any],
        strategy_id: str,
        user_id: str,
        db: Database,
        stream_publisher: Callable,
        initial_capital: float = 100000.0,
        session_id: Optional[str] = None,
        is_crypto: bool = False,
    ):
        self.alpaca = alpaca_client
        self.data_provider = data_provider
        self.db = db
        self.stream_publisher = stream_publisher
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.session_id = session_id
        self.is_crypto = is_crypto
        self._should_stop = False

        # Parse strategy configuration
        config = strategy_config.get("config", strategy_config)
        self.strategy_name = strategy_config.get("name", "Unnamed Strategy")
        self.symbols: List[str] = config.get("symbols", [])
        self.timeframe: str = config.get("timeframe", "15M")
        self.entry_conditions = config.get("entry_conditions", [])
        self.exit_conditions = config.get("exit_conditions", [])
        self.risk_management = config.get("risk_management", {})
        self.indicator_params = convert_indicators_to_params(config.get("indicators", []))

        # DCA settings
        dca_config = config.get("dollar_cost_averaging", config.get("dollar_cost_average", {}))
        self.dca_enabled = dca_config.get("enabled", False)
        self.max_dca_positions = dca_config.get("max_positions", 1)

        # Helpers
        self.condition_checker = ConditionChecker()
        self.trade_logger = TradeLogger()

        # Persistence
        self.persistence = PortfolioPersistence(
            db=db,
            stream_publisher=stream_publisher,
            strategy_id=strategy_id,
            user_id=user_id,
        )

        # Portfolio — attempt to load from DB, otherwise create fresh
        self.portfolio = self._load_or_create_portfolio(initial_capital)
        self.initial_capital = float(self.portfolio.initial_capital)

        logger.info(
            f"LiveStrategyRunner initialized: strategy={self.strategy_name}, "
            f"symbols={self.symbols}, timeframe={self.timeframe}, "
            f"initial_capital={self.initial_capital}, is_crypto={self.is_crypto}"
        )

    # ==================== PORTFOLIO LOAD / CREATE ====================

    def _load_or_create_portfolio(self, initial_capital: float) -> StrategyPortfolio:
        """
        Load an existing StrategyPortfolio from MongoDB if one exists for this
        strategy+user, otherwise create a new one.  This is the key to resumption.
        """
        try:
            doc = self.db.strategy_portfolios.find_one({
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
            })
            if doc:
                logger.info(f"Resuming portfolio from DB for strategy {self.strategy_id}")
                return self._deserialize_portfolio(doc, initial_capital)
        except Exception as e:
            logger.error(f"Error loading portfolio from DB: {e}")

        # No saved state — create fresh portfolio
        account_cash = self._safe_get_cash()
        effective_capital = max(initial_capital, account_cash)
        logger.info(
            f"Creating new portfolio: user_initial={initial_capital}, "
            f"account_cash={account_cash}, effective={effective_capital}"
        )

        return StrategyPortfolio(
            strategy_id=self.strategy_id,
            user_id=self.user_id,
            strategy_name=self.strategy_name,
            initial_capital=effective_capital,
            current_cash=Decimal(str(effective_capital)),
            performance=PerformanceMetrics(),
        )

    def _deserialize_portfolio(self, doc: Dict[str, Any], initial_capital: float) -> StrategyPortfolio:
        """
        Reconstruct a StrategyPortfolio from a MongoDB document.
        Handles type coercion for Decimal, datetime, etc.
        """
        from ...models.portfolio_models import PositionLot, CompletedTrade

        # Reconstruct lots
        lots: Dict[str, List[PositionLot]] = {}
        for symbol, lot_list in doc.get("lots", {}).items():
            lots[symbol] = []
            for lot_data in lot_list:
                lot_data.setdefault("strategy_id", self.strategy_id)
                lot_data.setdefault("user_id", self.user_id)
                lots[symbol].append(PositionLot(**lot_data))

        # Reconstruct completed trades
        completed_trades = []
        for trade_data in doc.get("completed_trades", []):
            trade_data.setdefault("strategy_id", self.strategy_id)
            trade_data.setdefault("user_id", self.user_id)
            completed_trades.append(CompletedTrade(**trade_data))

        # Reconstruct performance
        perf_data = doc.get("performance", {})
        performance = PerformanceMetrics(**perf_data) if perf_data else PerformanceMetrics()

        stored_capital = float(doc.get("initial_capital", initial_capital))
        effective_capital = max(stored_capital, initial_capital)

        portfolio = StrategyPortfolio(
            portfolio_id=doc.get("portfolio_id", str(doc.get("_id", ""))),
            strategy_id=str(doc.get("strategy_id", self.strategy_id)),
            user_id=str(doc.get("user_id", self.user_id)),
            strategy_name=doc.get("strategy_name", self.strategy_name),
            initial_capital=effective_capital,
            current_cash=doc.get("current_cash", effective_capital),
            lots=lots,
            completed_trades=completed_trades,
            performance=performance,
            is_active=doc.get("is_active", True),
        )

        logger.info(
            f"Restored portfolio: cash={portfolio.current_cash}, "
            f"lots={sum(len(v) for v in portfolio.lots.values())}, "
            f"trades={len(portfolio.completed_trades)}"
        )
        return portfolio

    # ==================== MAIN LOOP ====================

    def run(self):
        """
        Main blocking trading loop.  Called from the Celery task.
        Loops until self._should_stop is set or the task is revoked.
        """
        self._log("Starting live strategy runner", "INFO")

        while not self._should_stop:
            try:
                self._run_iteration()
            except Exception as e:
                logger.error(f"Error in trading iteration: {e}", exc_info=True)
                self._log(f"Error in iteration: {e}", "ERROR")

            sleep_seconds = self._get_sleep_seconds()
            logger.info(f"Sleeping {sleep_seconds}s until next iteration")
            # Sleep in small increments so we can respond to stop signals
            for _ in range(int(sleep_seconds)):
                if self._should_stop:
                    break
                time.sleep(1)

        self._log("Strategy runner stopped", "INFO")

    def stop(self):
        """Signal the runner to stop after the current iteration."""
        self._should_stop = True

    # ==================== SINGLE ITERATION ====================

    def _run_iteration(self):
        """Execute one full trading cycle."""
        now = datetime.now(tz=timezone.utc)
        self._log(f"=== Iteration at {now.isoformat()} ===")

        # --- Account info ---
        cash = self._safe_get_cash()
        self.portfolio.current_cash = Decimal(str(cash))
        self._log(f"Cash Balance: ${cash:,.2f}")

        # --- Fetch & process data per symbol ---
        portfolio_value = cash
        latest_prices: Dict[str, float] = {}
        asset_type = "crypto" if self.is_crypto else "stock"

        for symbol in self.symbols:
            try:
                self._process_symbol(symbol, asset_type, latest_prices)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                self._log(f"Error processing {symbol}: {e}", "ERROR")

        # --- Emit final account value with real portfolio value ---
        if latest_prices:
            positions_value = sum(
                float(lot.quantity) * latest_prices.get(symbol, 0)
                for symbol, lots in self.portfolio.lots.items()
                for lot in lots
            )
            portfolio_value = cash + positions_value
        self._publish_account_value(portfolio_value, cash)

        # --- Emit positions ---
        self._publish_positions()

        # --- End of iteration: update metrics and persist ---
        self.portfolio.update_performance_metrics()
        self.portfolio.update_equity_curve(
            {s: Decimal(str(p)) for s, p in latest_prices.items()}
        )

        self._publish_portfolio_snapshot()
        self.persistence.save_portfolio_snapshot(self.portfolio, latest_prices)
        self.persistence.sync_portfolio_to_db(self.portfolio)

        # Update session iteration
        self._update_session_iteration()

        self._log("=== Iteration complete ===")

    # ==================== SYMBOL PROCESSING ====================

    def _process_symbol(self, symbol: str, asset_type: str, latest_prices: Dict[str, float]):
        """Fetch data, compute indicators, check conditions, execute trades for one symbol."""

        # 1. Fetch historical data
        df = self._fetch_indicator_data(symbol, asset_type)
        if df is None or df.is_empty():
            self._log(f"No data for {symbol}, skipping")
            return

        # 2. Calculate indicators (includes _prev columns for crossover detection)
        technicals = IndicatorFactory(df, self.indicator_params)
        df_with_indicators = technicals.calculate_indicators()
        if df_with_indicators is None or df_with_indicators.is_empty():
            self._log(f"No indicators for {symbol}")
            return

        # 3. Log indicator data
        self._publish_indicator_data(symbol, df_with_indicators)
        self._publish_indicator_values(symbol, df_with_indicators)

        latest_data = df_with_indicators.row(-1, named=True)
        current_price = latest_data["close"]
        latest_prices[symbol] = current_price

        # 4. Check conditions & trade
        current_lots = self.portfolio.lots.get(symbol, [])
        has_position = len(current_lots) > 0

        # --- CHECK EXITS ---
        if has_position:
            should_exit, exit_details, _ = self.condition_checker.check_exit_conditions(
                conditions=self.exit_conditions, row=latest_data
            )
            if should_exit:
                exit_reason = self._build_exit_reason(exit_details)
                self._log(f"🔴 EXIT signal for {symbol}: {exit_reason}", "WARNING")
                self._publish_log(f"Exit conditions met for {symbol}: {exit_reason}", event_type=LogEventType.EXIT_CONDITIONS)
                self._execute_sell(symbol, current_price, exit_reason, asset_type)

        # Refresh lots after potential exit
        current_lots = self.portfolio.lots.get(symbol, [])
        current_lot_count = len(current_lots)

        # --- CHECK ENTRIES ---
        can_enter = (
            (self.dca_enabled and current_lot_count < self.max_dca_positions)
            or (not self.dca_enabled and current_lot_count == 0)
        )

        if can_enter:
            should_enter, _ = self.condition_checker.check_entry_conditions(
                conditions=self.entry_conditions, row=latest_data
            )
            if should_enter:
                self._log(f"🟢 ENTRY signal for {symbol}")
                self._execute_buy(symbol, current_price, latest_data, asset_type)

    # ==================== ORDER EXECUTION ====================

    def _execute_buy(self, symbol: str, price: float, latest_data: Dict, asset_type: str):
        """Calculate size, submit buy order, record lot."""
        qty = self._calculate_position_size(price, latest_data)
        if qty <= 0:
            self._log(f"Position size for {symbol} is 0, skipping buy")
            return

        # Normalize symbol for Alpaca API
        order_symbol = f"{symbol}/USD" if asset_type == "crypto" else symbol

        try:
            order = self.alpaca.submit_order(
                symbol=order_symbol,
                qty=round(qty, 6) if asset_type == "crypto" else round(qty, 2),
                side="buy",
                order_type="market",
                time_in_force="gtc",
            )

            # Wait for fill
            filled_order = self.alpaca.wait_for_order_fill(order["id"], timeout=30)
            fill_price = float(filled_order.get("filled_avg_price", price))
            fill_qty = float(filled_order.get("filled_qty", qty))

            if filled_order.get("status") not in ("filled", "partially_filled"):
                self._log(f"Buy order for {symbol} not filled: {filled_order.get('status')}", "WARNING")
                return

            # Record in portfolio
            new_lot = PositionLot(
                symbol=symbol,
                quantity=Decimal(str(fill_qty)),
                entry_price=Decimal(str(fill_price)),
                entry_time=datetime.now(tz=timezone.utc),
                cost_basis=Decimal(str(fill_qty)) * Decimal(str(fill_price)),
                entry_reason="Entry Signal",
                strategy_id=self.strategy_id,
                user_id=self.user_id,
                alpaca_order_id=order["id"],
            )
            self.portfolio.add_buy(new_lot)
            self.portfolio.current_cash -= new_lot.cost_basis

            # Persist
            self.persistence.save_buy(new_lot)

            self._log(f"✅ BUY: {fill_qty} {symbol} @ ${fill_price:.2f} (order {order['id']})")

        except Exception as e:
            logger.error(f"Buy order failed for {symbol}: {e}", exc_info=True)
            self._log(f"Buy order failed for {symbol}: {e}", "ERROR")

    def _execute_sell(self, symbol: str, price: float, reason: str, asset_type: str):
        """Sell all lots for a symbol.
        Uses close_position (DELETE /v2/positions) which is more reliable than
        a sell market order — avoids 403 Forbidden for crypto (short-sell ban)
        when the portfolio tracker is even slightly out of sync with Alpaca.
        Falls back to submit_order if close_position fails."""
        total_qty = float(self.portfolio.get_position_quantity(symbol))
        if total_qty <= 0:
            return

        order_symbol = f"{symbol}/USD" if asset_type == "crypto" else symbol

        try:
            # Prefer close_position — it asks Alpaca to liquidate whatever
            # quantity IT knows about, so there's no risk of accidentally
            # trying to short the asset (which causes 403 for crypto).
            try:
                order = self.alpaca.close_position(order_symbol)
                self._log(f"Close-position order submitted for {symbol} (order {order.get('id')})")
            except Exception as cp_err:
                logger.warning(f"close_position failed for {order_symbol}, falling back to market sell: {cp_err}")
                order = self.alpaca.submit_order(
                    symbol=order_symbol,
                    qty=round(total_qty, 6) if asset_type == "crypto" else round(total_qty, 2),
                    side="sell",
                    order_type="market",
                    time_in_force="gtc",
                )

            filled_order = self.alpaca.wait_for_order_fill(order["id"], timeout=30)
            fill_price = float(filled_order.get("filled_avg_price", price))

            if filled_order.get("status") not in ("filled", "partially_filled"):
                self._log(f"Sell order for {symbol} not filled: {filled_order.get('status')}", "WARNING")
                return

            # Process in portfolio
            completed_trades = self.portfolio.process_sell(
                symbol=symbol,
                quantity=Decimal(str(total_qty)),
                exit_price=Decimal(str(fill_price)),
                exit_time=datetime.now(tz=timezone.utc),
                reason=reason,
            )
            self.portfolio.update_performance_metrics()

            # Persist trades
            for trade in completed_trades:
                self.persistence.save_completed_trade(trade)
                self._log(
                    f"📈 TRADE CLOSED: {trade.symbol} | "
                    f"P&L: ${float(trade.realized_pnl):,.2f}"
                )

        except Exception as e:
            logger.error(f"Sell order failed for {symbol}: {e}", exc_info=True)
            self._log(f"Sell order failed for {symbol}: {e}", "ERROR")

    # ==================== DATA FETCHING ====================

    def _fetch_indicator_data(self, symbol: str, asset_type: str) -> Optional[pl.DataFrame]:
        """
        Fetch recent historical bars for indicator calculation.
        Uses the same AlpacaProvider that backtests use, called synchronously.
        """
        end_date = datetime.now(tz=timezone.utc)
        # Fetch enough bars for indicator calculation (50+ periods)
        lookback = self._calculate_lookback(self.timeframe, 100)
        start_date = end_date - timedelta(days=lookback)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if asset_type == "crypto":
                    df = loop.run_until_complete(
                        self.data_provider.get_historical_data(
                            symbols=[symbol],
                            start_date=start_date,
                            end_date=end_date,
                            timeframe=self.timeframe,
                        )
                    )
                else:
                    df = loop.run_until_complete(
                        self.data_provider.get_historical_data(
                            symbols=[symbol],
                            start_date=start_date,
                            end_date=end_date,
                            timeframe=self.timeframe,
                        )
                    )
            finally:
                loop.close()

            if df is None or (hasattr(df, "is_empty") and df.is_empty()):
                return None
            if isinstance(df, list):
                df = pl.concat(df) if df else None
                if df is None:
                    return None

            # Standardize columns
            rename_map = {"t": "datetime", "timestamp": "datetime"}
            for old, new in rename_map.items():
                if old in df.columns and new not in df.columns:
                    df = df.rename({old: new})

            # Normalize column names to lowercase
            df = df.rename({c: c.lower() for c in df.columns})

            # Ensure symbol column
            if "symbol" not in df.columns:
                df = df.with_columns(pl.lit(symbol).alias("symbol"))

            # Filter to just this symbol
            if "symbol" in df.columns:
                df = df.filter(pl.col("symbol") == symbol)

            return df.sort("datetime") if "datetime" in df.columns else df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
            return None

    # ==================== POSITION SIZING ====================

    def _calculate_position_size(self, price: float, latest_data: Dict) -> float:
        """Calculate position size based on risk management config."""
        if price <= 0:
            return 0.0

        cash = float(self.portfolio.current_cash)
        method = self.risk_management.get("method", "risk_based")
        risk_per_trade = self.risk_management.get("risk_per_trade", 0.01)
        amount_to_risk = cash * risk_per_trade

        if method == "atr_based":
            atr_multiplier = self.risk_management.get("atr_multiplier", 2.0)
            atr_key = next((k for k in latest_data if "atr" in k.lower()), None)
            if atr_key and latest_data.get(atr_key):
                stop_dist = latest_data[atr_key] * atr_multiplier
                if stop_dist > 0:
                    return amount_to_risk / stop_dist

        # Default: risk_based sizing
        return amount_to_risk / price

    # ==================== EVENT PUBLISHING ====================

    def _log(self, message: str, level: str = "INFO"):
        """Emit a log event to the Redis stream."""
        if level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

        if self.stream_publisher:
            self.stream_publisher("log", {
                "event_type": LogEventType.LOG,
                "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                "level": level,
                "message": str(message),
            })

    def _publish_log(self, message: str, level: str = "INFO", event_type=LogEventType.LOG):
        """Publish a log with a specific event_type for frontend rendering."""
        if self.stream_publisher:
            payload = {
                "event_type": event_type,
                "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                "level": level,
                "message": str(message),
            }
            # If message looks like JSON, parse it into data field
            if isinstance(message, str) and message.strip().startswith("{"):
                try:
                    payload["data"] = json.loads(message)
                except json.JSONDecodeError:
                    pass
            self.stream_publisher("log", payload)

    def _publish_positions(self):
        """Publish current positions for frontend."""
        positions_data = []
        for symbol, lots in self.portfolio.lots.items():
            for lot in lots:
                positions_data.append({
                    "symbol": symbol,
                    "quantity": float(lot.quantity),
                    "entry_price": float(lot.entry_price),
                    "lot_id": lot.lot_id,
                })

        payload = json.dumps({
            "title": f"Current Positions ({len(positions_data)} open)",
            "positions": positions_data,
        })
        self._publish_log(payload, event_type=LogEventType.POSITIONS)

    def _publish_account_value(self, total_value: float, cash: float):
        """Publish account value for frontend equity chart + metrics."""
        payload = json.dumps({
            "title": f"Account Value: ${total_value:,.2f}",
            "account_value": total_value,
            "cash": cash,
        })
        self._publish_log(payload, event_type=LogEventType.ACCOUNT_VALUE)

    def _publish_indicator_data(self, symbol: str, df: pl.DataFrame):
        """Publish the last N rows of indicator data for frontend table."""
        try:
            df_to_log = df.tail(2).with_columns(pl.col(pl.Float64).round(4))
            df_json = df_to_log.write_json()
            log_payload = {
                "type": "dataframe",
                "title": f"Technical Indicators for {symbol}",
                "data": json.loads(df_json),
            }
            self._publish_log(json.dumps(log_payload, indent=4), event_type=LogEventType.PRICE_DATAFRAME)
        except Exception as e:
            logger.error(f"Error publishing indicator data: {e}")

    def _publish_indicator_values(self, symbol: str, df: pl.DataFrame):
        """Publish indicator time-series for frontend charting.

        Sends the last 100 rows of datetime + all computed indicator columns
        so the frontend can render one chart per indicator (SMA, MACD, BBands,
        RSI, etc.).
        """
        try:
            # OHLCV + internal columns to exclude — keep only indicator columns
            base_cols = {"open", "high", "low", "close", "volume", "symbol",
                         "datetime", "trade_count", "vwap"}
            indicator_cols = [c for c in df.columns
                             if c.lower() not in base_cols
                             and not c.endswith("_prev")]  # skip _prev helper cols

            if not indicator_cols:
                return

            # Keep datetime + close (for overlay reference) + indicator cols
            keep = ["datetime", "close"] + indicator_cols
            keep = [c for c in keep if c in df.columns]
            subset = df.select(keep).tail(100)
            subset = subset.with_columns(pl.col(pl.Float64).round(6))

            rows = json.loads(subset.write_json())

            if self.stream_publisher:
                self.stream_publisher("indicator_values", {
                    "event_type": LogEventType.INDICATOR_VALUES,
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "symbol": symbol,
                    "columns": indicator_cols,
                    "rows": rows,
                })
        except Exception as e:
            logger.error(f"Error publishing indicator values: {e}", exc_info=True)

    def _publish_portfolio_snapshot(self):
        """Publish full portfolio snapshot for frontend."""
        self._publish_log(
            self.portfolio.model_dump_json(indent=4, exclude={"user_id", "strategy_id"}),
            event_type=LogEventType.PORTFOLIO_SNAPSHOT,
        )

    # ==================== SESSION MANAGEMENT ====================

    def _update_session_iteration(self):
        """Update trading session document with latest iteration info."""
        if not self.session_id:
            return
        try:
            self.db.trading_sessions.update_one(
                {"session_id": self.session_id},
                {
                    "$set": {
                        "last_iteration_at": datetime.now(tz=timezone.utc),
                        "updated_at": datetime.now(tz=timezone.utc),
                        "status": "active",
                    },
                    "$inc": {"iteration_count": 1},
                },
            )
        except Exception as e:
            logger.error(f"Error updating session: {e}")

    # ==================== UTILITIES ====================

    def _safe_get_cash(self) -> float:
        """Get cash with error handling."""
        try:
            return self.alpaca.get_cash()
        except Exception as e:
            logger.error(f"Error getting cash from Alpaca: {e}")
            return float(self.portfolio.current_cash)

    def _build_exit_reason(self, exit_details) -> str:
        """Build human-readable exit reason from condition details."""
        if not exit_details:
            return "Strategy Exit"
        fired = [
            self.exit_conditions[i].get("indicator", "unknown")
            for i, met in enumerate(exit_details)
            if met
        ]
        return f"Exit: {', '.join(fired)}" if fired else "Strategy Exit"

    def _get_sleep_seconds(self) -> int:
        """Convert timeframe to sleep duration in seconds."""
        tf = self.timeframe.upper()
        if "MIN" in tf:
            return int(tf.replace("MIN", "").replace("M", "")) * 60
        if "HOUR" in tf or tf.endswith("H"):
            return 3600
        if "DAY" in tf or tf.endswith("D"):
            return 86400
        if tf == "10S":
            return 10
        # Default: 60 seconds
        return 60

    @staticmethod
    def _calculate_lookback(timeframe: str, periods: int = 100) -> int:
        """Calculate lookback days needed for the given timeframe and periods."""
        tf = timeframe.upper()
        if "MIN" in tf or tf.endswith("M"):
            mins = int("".join(filter(str.isdigit, tf)) or "15")
            points_per_day = 390 / mins  # ~6.5 trading hours
            return max(7, int(periods / points_per_day) * 2)
        if "HOUR" in tf or tf.endswith("H"):
            return max(14, int(periods / 6.5) * 2)
        if "DAY" in tf or tf.endswith("D"):
            return periods * 2
        if "W" in tf:
            return periods * 10
        return periods * 2
