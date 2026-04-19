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
from ...services.data_retrieval.data_providers import (
    AlpacaProvider,
    AVAILABLE_CRYPTO_ASSETS,
)
from ...utils.asset_classifier import is_within_market_hours
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
        extended_hours: bool = False,
        mode: str = "paper",
    ):
        self.alpaca = alpaca_client
        self.data_provider = data_provider
        self.db = db
        self.stream_publisher = stream_publisher
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.session_id = session_id
        self.is_crypto = is_crypto
        self.extended_hours = extended_hours
        self.mode = mode
        self._should_stop = False
        self._exited_market_hours = False

        # Parse strategy configuration
        config = strategy_config.get("config", strategy_config)
        self.strategy_name = strategy_config.get("name", "Unnamed Strategy")
        self.symbols: List[str] = config.get("symbols", [])
        self.timeframe: str = config.get("timeframe", "15M")
        self.entry_conditions = config.get("entry_conditions", [])
        self.exit_conditions = config.get("exit_conditions", [])
        self.risk_management = config.get("risk_management", {})
        self.indicator_params = convert_indicators_to_params(
            config.get("indicators", [])
        )

        # DCA settings
        dca_config = config.get(
            "dollar_cost_averaging", config.get("dollar_cost_average", {})
        )
        self.dca_enabled = dca_config.get("enabled", False)
        self.max_dca_positions = dca_config.get(
            "max_positions", dca_config.get("max_attempts", 1)
        )
        self.dca_interval_seconds = self._parse_interval(
            dca_config.get("interval", "0")
        )
        self.dca_amount_per_attempt = float(dca_config.get("amount_per_attempt", 0))

        # Helpers
        self.condition_checker = ConditionChecker()
        self.trade_logger = TradeLogger()

        # Persistence
        self.persistence = PortfolioPersistence(
            db=db,
            stream_publisher=stream_publisher,
            strategy_id=strategy_id,
            user_id=user_id,
            mode=mode,
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
            doc = self.db.strategy_portfolios.find_one(
                {
                    "strategy_id": self.strategy_id,
                    "user_id": self.user_id,
                    "mode": self.mode,
                }
            )
            if doc:
                logger.info(
                    f"Resuming portfolio from DB for strategy {self.strategy_id}"
                )
                portfolio = self._deserialize_portfolio(doc, initial_capital)
                # Assign early so _reconcile_positions can call _reconcile_phantom_position
                self.portfolio = portfolio
                self._reconcile_positions(portfolio)
                return portfolio
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

    def _reconcile_positions(self, portfolio: StrategyPortfolio) -> None:
        """
        Compare MongoDB portfolio positions against actual Alpaca positions.
        Auto-reconciles phantom positions (portfolio has lots but broker does not).
        """
        try:
            alpaca_positions = self.alpaca.get_positions()

            # Normalize Alpaca symbols: crypto comes back as DOGEUSD, strip /USD or USD suffix
            def normalize_sym(s):
                if s and s.endswith("USD") and "/" not in s and len(s) > 3:
                    return s[:-3]  # DOGEUSD -> DOGE, BTCUSD -> BTC
                return s.replace("/USD", "") if s else s

            alpaca_symbols = {normalize_sym(p.get("symbol")) for p in alpaca_positions}
            portfolio_symbols = {s for s, lots in portfolio.lots.items() if lots}

            portfolio_lot_count = sum(len(lots) for lots in portfolio.lots.values())
            alpaca_position_count = len(alpaca_positions)

            if (
                portfolio_symbols != alpaca_symbols
                or portfolio_lot_count != alpaca_position_count
            ):
                logger.warning(
                    f"POSITION MISMATCH on resume — "
                    f"MongoDB lots: {portfolio_lot_count} across {sorted(portfolio_symbols)}, "
                    f"Alpaca positions: {alpaca_position_count} across {sorted(alpaca_symbols)}"
                )
                # Auto-reconcile phantom positions (portfolio has lots but broker does not)
                phantom_symbols = portfolio_symbols - alpaca_symbols
                for sym in phantom_symbols:
                    lots = portfolio.lots.get(sym, [])
                    avg_entry = (
                        float(sum(lot.entry_price for lot in lots) / len(lots))
                        if lots
                        else 0.0
                    )
                    try:
                        quote = self.alpaca.get_latest_quote(
                            sym,
                            asset_type="crypto"
                            if sym in AVAILABLE_CRYPTO_ASSETS
                            else "stock",
                        )
                        exit_price = quote.get("price", avg_entry) or avg_entry
                    except Exception:
                        exit_price = avg_entry
                    self._reconcile_phantom_position(
                        sym, exit_price, "Phantom position reconciled on startup"
                    )
            else:
                logger.info(
                    f"Position reconciliation OK: {portfolio_lot_count} lots, "
                    f"symbols={sorted(portfolio_symbols)}"
                )
        except Exception as e:
            logger.error(f"Position reconciliation failed (non-fatal): {e}")

    def _deserialize_portfolio(
        self, doc: Dict[str, Any], initial_capital: float
    ) -> StrategyPortfolio:
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
        performance = (
            PerformanceMetrics(**perf_data) if perf_data else PerformanceMetrics()
        )

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
            # Stock strategies exit when market closes; Beat restarts at next open
            if not self.is_crypto and not self._is_within_trading_hours():
                self._log("Market closed — exiting until next scheduled open", "INFO")
                self._exited_market_hours = True
                break

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

    def _is_within_trading_hours(self) -> bool:
        """Check whether the current time is within the strategy's trading window."""
        return is_within_market_hours(extended=self.extended_hours)

    # ==================== SINGLE ITERATION ====================

    def _run_iteration(self):
        """Execute one full trading cycle."""
        now = datetime.now(tz=timezone.utc)
        self._log(f"=== Iteration at {now.isoformat()} ===")

        # --- Account info ---
        cash = self._safe_get_cash()
        self.portfolio.current_cash = Decimal(str(cash))
        self._log(f"Cash Balance: ${cash:,.2f}")

        # --- Reconcile positions with Alpaca before processing ---
        self._reconcile_positions(self.portfolio)

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

    def _process_symbol(
        self, symbol: str, asset_type: str, latest_prices: Dict[str, float]
    ):
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

        # Debug: log computed indicator columns
        _base = {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "datetime",
            "trade_count",
            "vwap",
        }
        _computed = [
            c
            for c in df_with_indicators.columns
            if c.lower() not in _base and not c.endswith("_prev")
        ]
        self._log(f"Indicator params: {self.indicator_params}")
        self._log(f"Indicator columns for {symbol}: {_computed}")
        self._log(f"All DataFrame columns: {df_with_indicators.columns}")

        # 3. Log indicator data
        self._publish_indicator_data(symbol, df_with_indicators)
        self._publish_indicator_values(symbol, df_with_indicators)

        latest_data = df_with_indicators.row(-1, named=True)
        current_price = latest_data["close"]
        latest_prices[symbol] = current_price

        # 4. Check conditions & trade
        current_lots = self.portfolio.lots.get(symbol, [])
        has_position = len(current_lots) > 0

        # --- CHECK SL/TP PER LOT (price-based exits) ---
        if has_position:
            lots_to_exit = []
            for lot in current_lots:
                if lot.stop_loss_price and current_price <= float(lot.stop_loss_price):
                    lots_to_exit.append((lot, "Stop Loss"))
                    self._log(
                        f"🛑 STOP LOSS hit for {symbol} lot {lot.lot_id[:8]}: "
                        f"price ${current_price:.4f} <= SL ${float(lot.stop_loss_price):.4f}",
                        "WARNING",
                    )
                elif lot.take_profit_price and current_price >= float(
                    lot.take_profit_price
                ):
                    lots_to_exit.append((lot, "Take Profit"))
                    self._log(
                        f"🎯 TAKE PROFIT hit for {symbol} lot {lot.lot_id[:8]}: "
                        f"price ${current_price:.4f} >= TP ${float(lot.take_profit_price):.4f}",
                    )
            for lot, reason in lots_to_exit:
                self._execute_sell_lot(symbol, lot, current_price, reason, asset_type)

        # Refresh lots after SL/TP exits
        current_lots = self.portfolio.lots.get(symbol, [])
        has_position = len(current_lots) > 0

        # --- CHECK INDICATOR-BASED EXITS ---
        if has_position:
            should_exit, exit_details, _ = self.condition_checker.check_exit_conditions(
                conditions=self.exit_conditions, row=latest_data
            )
            if should_exit:
                exit_reason = self._build_exit_reason(exit_details)
                self._log(f"🔴 EXIT signal for {symbol}: {exit_reason}", "WARNING")
                self._publish_log(
                    f"Exit conditions met for {symbol}: {exit_reason}",
                    event_type=LogEventType.EXIT_CONDITIONS,
                )
                self._execute_sell(symbol, current_price, exit_reason, asset_type)

        # Refresh lots after potential exit
        current_lots = self.portfolio.lots.get(symbol, [])
        current_lot_count = len(current_lots)

        # --- CHECK ENTRIES ---
        is_dca_entry = self.dca_enabled and current_lot_count > 0
        can_enter = (
            self.dca_enabled and current_lot_count < self.max_dca_positions
        ) or (not self.dca_enabled and current_lot_count == 0)

        # Enforce DCA interval
        if can_enter and is_dca_entry and self.dca_interval_seconds > 0:
            latest_lot = max(current_lots, key=lambda lot: lot.entry_time)
            lot_entry = (
                latest_lot.entry_time
                if latest_lot.entry_time.tzinfo
                else latest_lot.entry_time.replace(tzinfo=timezone.utc)
            )
            elapsed = (datetime.now(tz=timezone.utc) - lot_entry).total_seconds()
            if elapsed < self.dca_interval_seconds:
                can_enter = False
                self._log(
                    f"DCA interval not met for {symbol}: {elapsed:.0f}s / {self.dca_interval_seconds}s",
                    "DEBUG",
                )

        if can_enter:
            should_enter, _ = self.condition_checker.check_entry_conditions(
                conditions=self.entry_conditions, row=latest_data
            )
            if should_enter:
                self._log(
                    f"🟢 ENTRY signal for {symbol}" + (" (DCA)" if is_dca_entry else "")
                )
                self._execute_buy(
                    symbol, current_price, latest_data, asset_type, is_dca=is_dca_entry
                )

    # ==================== ORDER EXECUTION ====================

    def _execute_buy(
        self,
        symbol: str,
        price: float,
        latest_data: Dict,
        asset_type: str,
        is_dca: bool = False,
    ):
        """Calculate size, submit buy order, record lot with SL/TP prices."""
        qty = self._calculate_position_size(price, latest_data, is_dca=is_dca)
        if qty <= 0:
            self._log(f"Position size for {symbol} is 0, skipping buy")
            return

        # Alpaca requires minimum order cost basis of $1
        cost_basis = qty * price
        if cost_basis < 1.0:
            self._log(
                f"Order cost basis ${cost_basis:.2f} is below Alpaca's $1 minimum for {symbol}, skipping buy",
                "WARNING",
            )
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
                self._log(
                    f"Buy order for {symbol} not filled: {filled_order.get('status')}",
                    "WARNING",
                )
                return

            # Calculate SL/TP prices for this lot
            sl_price, tp_price = self._calculate_sl_tp(fill_price, latest_data)

            # Record in portfolio
            new_lot = PositionLot(
                symbol=symbol,
                quantity=Decimal(str(fill_qty)),
                entry_price=Decimal(str(fill_price)),
                entry_time=datetime.now(tz=timezone.utc),
                cost_basis=Decimal(str(fill_qty)) * Decimal(str(fill_price)),
                entry_reason="DCA Entry" if is_dca else "Entry Signal",
                strategy_id=self.strategy_id,
                user_id=self.user_id,
                alpaca_order_id=order["id"],
                stop_loss_price=Decimal(str(sl_price)) if sl_price else None,
                take_profit_price=Decimal(str(tp_price)) if tp_price else None,
            )
            self.portfolio.add_buy(new_lot)
            self.portfolio.current_cash -= new_lot.cost_basis

            # Persist
            self.persistence.save_buy(new_lot)

            sl_str = f" SL=${sl_price:.4f}" if sl_price else ""
            tp_str = f" TP=${tp_price:.4f}" if tp_price else ""
            self._log(
                f"✅ BUY: {fill_qty} {symbol} @ ${fill_price:.4f}{sl_str}{tp_str} (order {order['id']})"
            )

        except Exception as e:
            logger.error(f"Buy order failed for {symbol}: {e}", exc_info=True)
            self._log(f"Buy order failed for {symbol}: {e}", "ERROR")

    def _calculate_sl_tp(self, fill_price: float, latest_data: Dict):
        """Calculate stop loss and take profit prices for a new lot.

        ATR-based SL takes priority when ATR data is available and atr_multiplier
        is configured.  Otherwise falls back to percentage-based.
        Take profit is always percentage-based.
        """
        stop_loss_pct = self.risk_management.get("stop_loss", 0)
        take_profit_pct = self.risk_management.get("take_profit", 0)
        atr_multiplier = self.risk_management.get("atr_multiplier", 0)

        sl_price = None
        tp_price = None

        # Stop loss
        if atr_multiplier and atr_multiplier > 0:
            atr_value = self._get_atr_value(latest_data)
            if atr_value and atr_value > 0:
                sl_price = fill_price - (atr_value * atr_multiplier)
            elif stop_loss_pct and stop_loss_pct > 0:
                sl_price = fill_price * (1 - stop_loss_pct)
        elif stop_loss_pct and stop_loss_pct > 0:
            sl_price = fill_price * (1 - stop_loss_pct)

        # Take profit (always percentage-based)
        if take_profit_pct and take_profit_pct > 0:
            tp_price = fill_price * (1 + take_profit_pct)

        # Ensure SL is positive
        if sl_price is not None and sl_price <= 0:
            sl_price = None

        return sl_price, tp_price

    def _execute_sell(self, symbol: str, price: float, reason: str, asset_type: str):
        """Sell all lots for a symbol.
        Uses close_position (DELETE /v2/positions) which is more reliable than
        a sell market order — avoids 403 Forbidden for crypto (short-sell ban)
        when the portfolio tracker is even slightly out of sync with Alpaca.
        Falls back to submit_order if close_position fails.

        If the broker has no position at all, reconciles the phantom lots
        in the internal portfolio so the bot does not retry every iteration."""
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
                self._log(
                    f"Close-position order submitted for {symbol} (order {order.get('id')})"
                )
            except Exception as cp_err:
                logger.warning(f"close_position failed for {order_symbol}: {cp_err}")
                # Check whether the broker actually holds this position
                broker_pos = self.alpaca.get_position(order_symbol)
                if broker_pos is None:
                    # Broker has nothing — reconcile the phantom position
                    self._reconcile_phantom_position(symbol, price, reason)
                    return
                # Broker does have a position — fall back to market sell
                order = self.alpaca.submit_order(
                    symbol=order_symbol,
                    qty=round(total_qty, 6)
                    if asset_type == "crypto"
                    else round(total_qty, 2),
                    side="sell",
                    order_type="market",
                    time_in_force="gtc",
                )

            filled_order = self.alpaca.wait_for_order_fill(order["id"], timeout=30)
            fill_price = float(filled_order.get("filled_avg_price", price))

            if filled_order.get("status") not in ("filled", "partially_filled"):
                self._log(
                    f"Sell order for {symbol} not filled: {filled_order.get('status')}",
                    "WARNING",
                )
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

    def _execute_sell_lot(
        self, symbol: str, lot: PositionLot, price: float, reason: str, asset_type: str
    ):
        """Sell a single lot (used for per-lot SL/TP exits)."""
        lot_qty = float(lot.quantity)
        if lot_qty <= 0:
            return

        order_symbol = f"{symbol}/USD" if asset_type == "crypto" else symbol

        try:
            order = self.alpaca.submit_order(
                symbol=order_symbol,
                qty=round(lot_qty, 6) if asset_type == "crypto" else round(lot_qty, 2),
                side="sell",
                order_type="market",
                time_in_force="gtc",
            )

            filled_order = self.alpaca.wait_for_order_fill(order["id"], timeout=30)
            fill_price = float(filled_order.get("filled_avg_price", price))

            if filled_order.get("status") not in ("filled", "partially_filled"):
                self._log(
                    f"Sell lot order for {symbol} not filled: {filled_order.get('status')}",
                    "WARNING",
                )
                return

            # Process in portfolio (sell exactly this lot's quantity)
            completed_trades = self.portfolio.process_sell(
                symbol=symbol,
                quantity=lot.quantity,
                exit_price=Decimal(str(fill_price)),
                exit_time=datetime.now(tz=timezone.utc),
                reason=reason,
            )
            self.portfolio.update_performance_metrics()

            for trade in completed_trades:
                self.persistence.save_completed_trade(trade)
                self._log(
                    f"📈 LOT CLOSED ({reason}): {trade.symbol} | "
                    f"Entry ${float(trade.entry_price):.4f} → Exit ${float(trade.exit_price):.4f} | "
                    f"P&L: ${float(trade.realized_pnl):,.2f}"
                )

        except Exception as e:
            # Check if the broker has no position — if so, reconcile
            try:
                lot_order_symbol = f"{symbol}/USD" if asset_type == "crypto" else symbol
                broker_pos = self.alpaca.get_position(lot_order_symbol)
            except Exception:
                broker_pos = "unknown"  # can't determine — don't reconcile
            if broker_pos is None:
                self._reconcile_phantom_position(symbol, price, reason)
            else:
                logger.error(
                    f"Sell lot order failed for {symbol} ({reason}): {e}", exc_info=True
                )
                self._log(
                    f"Sell lot order failed for {symbol} ({reason}): {e}", "ERROR"
                )

    def _reconcile_phantom_position(self, symbol: str, price: float, reason: str):
        """Clear a phantom position from the internal portfolio.

        Called when the broker confirms it has no position.  Generates
        CompletedTrade records at the given price so P&L is tracked,
        persists them, and removes the lots."""
        total_qty = float(self.portfolio.get_position_quantity(symbol))
        if total_qty <= 0:
            return

        self._log(
            f"⚠️ PHANTOM POSITION RECONCILED: {symbol} — broker has no position, "
            f"clearing {total_qty} from portfolio at ${price:.4f}",
            "WARNING",
        )
        # Notify the user that this position was sold outside of BotClub
        self._publish_log(
            f"⚠️ {symbol} was sold outside of BotClub (e.g. on Alpaca's website). "
            f"Reconciling {total_qty:,.6f} shares at ${price:.4f}. "
            f"This position has been removed from the strategy.",
            event_type=LogEventType.LOG,
        )

        try:
            completed_trades = self.portfolio.process_sell(
                symbol=symbol,
                quantity=Decimal(str(total_qty)),
                exit_price=Decimal(str(price)),
                exit_time=datetime.now(tz=timezone.utc),
                reason=f"Phantom position reconciled — {reason}",
            )
            self.portfolio.update_performance_metrics()

            for trade in completed_trades:
                self.persistence.save_completed_trade(trade)
                self._log(
                    f"📈 PHANTOM TRADE CLOSED: {trade.symbol} | "
                    f"Entry ${float(trade.entry_price):.4f} → Reconciled Exit ${float(trade.exit_price):.4f} | "
                    f"P&L: ${float(trade.realized_pnl):,.2f}"
                )

            self._publish_portfolio_snapshot()
            self.persistence.sync_portfolio_to_db(self.portfolio)
        except Exception as e:
            # Last resort: force-clear the lots so we don't loop forever
            logger.error(
                f"Reconciliation process_sell failed for {symbol}: {e}", exc_info=True
            )
            self.portfolio.lots.pop(symbol, None)
            self.persistence.sync_portfolio_to_db(self.portfolio)
            self._log(
                f"Force-cleared phantom lots for {symbol} after reconciliation error",
                "ERROR",
            )

    # ==================== DATA FETCHING ====================

    def _fetch_indicator_data(
        self, symbol: str, asset_type: str
    ) -> Optional[pl.DataFrame]:
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
                # self._log(f"Filtered DataFrame for {symbol}: {df}")
            return df.sort("datetime") if "datetime" in df.columns else df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
            return None

    # ==================== POSITION SIZING ====================

    def _calculate_position_size(
        self, price: float, latest_data: Dict, is_dca: bool = False
    ) -> float:
        """Calculate position size based on risk management config.

        Supported ``position_sizing_method`` values:
        * ``risk_based`` – risk amount / dollar‑risk per share (uses stop_loss %)
        * ``percentage`` – percentage of cash / price
        * ``atr_based``  – risk amount / (ATR × multiplier)
        * ``fixed``      – risk_per_trade treated as a fixed dollar amount

        The result is clamped to ``max_position_size`` (in dollars).
        When DCA is enabled with ``amount_per_attempt > 0`` it overrides the
        method‑based quantity.
        """
        if price <= 0:
            return 0.0

        cash = float(self.portfolio.current_cash)

        # --- DCA override: use amount_per_attempt for sizing ---
        if is_dca and self.dca_amount_per_attempt > 0:
            qty = self.dca_amount_per_attempt / price
            return self._clamp_to_max_position(qty, price)

        method = self.risk_management.get(
            "position_sizing_method",
            self.risk_management.get("method", "risk_based"),
        )
        risk_per_trade = self.risk_management.get("risk_per_trade", 0.02)
        stop_loss_pct = self.risk_management.get("stop_loss", 0.05)
        atr_multiplier = self.risk_management.get("atr_multiplier", 2.0)
        amount_to_risk = cash * risk_per_trade

        if method == "atr_based":
            atr_value = self._get_atr_value(latest_data)
            if atr_value and atr_value > 0:
                stop_dist = atr_value * atr_multiplier
                qty = amount_to_risk / stop_dist
                return self._clamp_to_max_position(qty, price)
            # Fallback to risk_based when ATR unavailable
            self._log(
                "ATR data unavailable, falling back to risk_based sizing", "WARNING"
            )

        if method == "risk_based" or method == "atr_based":
            # risk_amount / (price × stop_loss_pct)
            dollar_risk_per_share = (
                price * stop_loss_pct if stop_loss_pct > 0 else price
            )
            qty = amount_to_risk / dollar_risk_per_share
            return self._clamp_to_max_position(qty, price)

        if method == "percentage":
            # risk_per_trade treated as fraction of cash
            qty = (cash * risk_per_trade) / price
            return self._clamp_to_max_position(qty, price)

        if method == "fixed":
            # risk_per_trade treated as a fixed dollar amount
            qty = risk_per_trade / price
            return self._clamp_to_max_position(qty, price)

        # Unknown method — default to percentage
        qty = (cash * risk_per_trade) / price
        return self._clamp_to_max_position(qty, price)

    def _clamp_to_max_position(self, qty: float, price: float) -> float:
        """Enforce max_position_size cap (in dollars)."""
        max_pos = self.risk_management.get("max_position_size", 0)
        if max_pos and max_pos > 0:
            max_qty = max_pos / price
            if qty > max_qty:
                self._log(
                    f"Position clamped to max_position_size ${max_pos:.0f} ({max_qty:.4f} units)"
                )
                return max_qty
        return qty

    def _get_atr_value(self, latest_data: Dict) -> Optional[float]:
        """Extract ATR value from latest indicator data."""
        atr_key = next((k for k in latest_data if "atr" in k.lower()), None)
        if atr_key and latest_data.get(atr_key):
            return float(latest_data[atr_key])
        return None

    @staticmethod
    def _parse_interval(interval_str: str) -> int:
        """Parse interval string like '1h', '30m', '1d' to seconds."""
        if not interval_str:
            return 0
        interval_str = interval_str.strip().lower()
        if interval_str == "0" or interval_str == "":
            return 0
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        for suffix, mult in multipliers.items():
            if interval_str.endswith(suffix):
                try:
                    return int(float(interval_str[:-1]) * mult)
                except ValueError:
                    return 0
        # Try parsing as raw seconds
        try:
            return int(interval_str)
        except ValueError:
            return 0

    # ==================== EVENT PUBLISHING ====================

    def _log(self, message: str, level: str = "INFO"):
        """Emit a log event to the Redis stream."""
        if level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

        if self.stream_publisher:
            self.stream_publisher(
                "log",
                {
                    "event_type": LogEventType.LOG,
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "level": level,
                    "message": str(message),
                },
            )

    def _publish_log(
        self, message: str, level: str = "INFO", event_type=LogEventType.LOG
    ):
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
                positions_data.append(
                    {
                        "symbol": symbol,
                        "quantity": float(lot.quantity),
                        "entry_price": float(lot.entry_price),
                        "lot_id": lot.lot_id,
                    }
                )

        payload = json.dumps(
            {
                "title": f"Current Positions ({len(positions_data)} open)",
                "positions": positions_data,
            }
        )
        self._publish_log(payload, event_type=LogEventType.POSITIONS)

    def _publish_account_value(self, total_value: float, cash: float):
        """Publish account value for frontend equity chart + metrics."""
        payload = json.dumps(
            {
                "title": f"Account Value: ${total_value:,.2f}",
                "account_value": total_value,
                "cash": cash,
            }
        )
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
            self._publish_log(
                json.dumps(log_payload, indent=4),
                event_type=LogEventType.PRICE_DATAFRAME,
            )
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
            base_cols = {
                "open",
                "high",
                "low",
                "close",
                "volume",
                "symbol",
                "datetime",
                "trade_count",
                "vwap",
            }
            indicator_cols = [
                c
                for c in df.columns
                if c.lower() not in base_cols and not c.endswith("_prev")
            ]  # skip _prev helper cols

            if not indicator_cols:
                return

            # Keep datetime + OHLCV (for candlestick chart) + indicator cols
            keep = ["datetime", "open", "high", "low", "close"] + indicator_cols
            keep = [c for c in keep if c in df.columns]
            subset = df.select(keep).tail(100)
            subset = subset.with_columns(pl.col(pl.Float64).round(6))

            rows = json.loads(subset.write_json())

            if self.stream_publisher:
                self.stream_publisher(
                    "indicator_values",
                    {
                        "event_type": LogEventType.INDICATOR_VALUES,
                        "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                        "symbol": symbol,
                        "columns": indicator_cols,
                        "rows": rows,
                    },
                )
        except Exception as e:
            logger.error(f"Error publishing indicator values: {e}", exc_info=True)

    def _publish_portfolio_snapshot(self):
        """Publish full portfolio snapshot for frontend."""
        self._publish_log(
            self.portfolio.model_dump_json(
                indent=4, exclude={"user_id", "strategy_id"}
            ),
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
            if hasattr(self, "portfolio") and self.portfolio:
                return float(self.portfolio.current_cash)
            return 0.0

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
