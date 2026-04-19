import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from .db_executor import run_db_operation

logger = logging.getLogger(__name__)


class TradeLogger:
    """Handles logging and storing trade information"""

    def __init__(self):
        self.trades: List[Dict[str, Any]] = []
        self.trade_count = 0
        self.collection_name = "deployed_strategies"

    def log_trade(
        self,
        symbol: str,
        entry_time: datetime,
        exit_time: datetime,
        entry_price: float,
        exit_price: float,
        quantity: float,
        pnl: float,
        trade_type: str = "long",
        strategy_name: str = "",
        entry_reason: str = "",
        exit_reason: str = "",
        data_context: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Log a completed trade"""
        self.trade_count += 1

        # Add emoji based on P&L
        pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"

        trade = {
            "trade_id": self.trade_count,
            "symbol": symbol.upper(),
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "quantity": quantity,
            "pnl": round(pnl, 2),
            "return_pct": round((pnl / (entry_price * quantity)) * 100, 2),
            "trade_type": trade_type,
            "strategy_name": strategy_name,
            "entry_reason": entry_reason,
            "exit_reason": exit_reason,
            "duration": (exit_time - entry_time).total_seconds()
            / 3600,  # This line correctly calculates duration for each trade.
            "timestamp": datetime.now(tz=timezone.utc),
            "pnl_emoji": pnl_emoji,
            "data_context": data_context or [],
        }

        self.trades.append(trade)

        # Log trade details with emoji
        logger.info(
            f"Trade {self.trade_count}: {pnl_emoji} {symbol} {trade_type.upper()} "
            f"Entry: ${entry_price:.4f} Exit: ${exit_price:.4f} "
            f"P&L: ${pnl:.2f} ({trade['return_pct']:.2f}%)"
        )

        return trade

    def log_entry_signal(
        self, symbol: str, timestamp: datetime, price: float, strategy_name: str = ""
    ) -> Dict[str, Any]:
        """Log an entry signal"""
        entry_signal = {
            "symbol": symbol.upper(),
            "timestamp": timestamp,
            "price": round(price, 4),
            "signal_type": "entry",
            "strategy_name": strategy_name,
        }

        logger.info(f"🟡 Entry signal: {symbol} at ${price:.4f}")
        return entry_signal

    def log_exit_signal(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        reason: str = "",
        signal_strength: float = 1.0,
        strategy_name: str = "",
    ) -> Dict[str, Any]:
        """Log an exit signal"""
        exit_signal = {
            "symbol": symbol.upper(),
            "timestamp": timestamp,
            "price": round(price, 4),
            "signal_type": "exit",
            "reason": reason,
            "signal_strength": signal_strength,
            "strategy_name": strategy_name,
        }

        logger.info(f"🟡 Exit signal: {symbol} at ${price:.4f} - {reason}")
        return exit_signal

    def get_trade_summary(self) -> Dict[str, Any]:
        """Get summary of all logged trades"""
        if not self.trades:
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
            }

        total_pnl = sum(trade["pnl"] for trade in self.trades)
        winning_trades = len([t for t in self.trades if t["pnl"] > 0])
        losing_trades = len([t for t in self.trades if t["pnl"] < 0])
        win_rate = (winning_trades / len(self.trades)) * 100 if self.trades else 0

        # Add emoji to summary
        summary_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"

        return {
            "total_trades": len(self.trades),
            "total_pnl": round(total_pnl, 2),
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "avg_trade_pnl": round(total_pnl / len(self.trades), 2)
            if self.trades
            else 0,
            "summary_emoji": summary_emoji,
        }

    def get_trades_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Get all trades for a specific symbol"""
        return [
            trade for trade in self.trades if trade["symbol"].upper() == symbol.upper()
        ]

    def print_trade_summary(self):
        """Print trade summary to logs with emoji"""
        summary = self.get_trade_summary()
        emoji = summary.get("summary_emoji", "⚪")
        logger.info(
            f"Trade Summary: {emoji} {summary['total_trades']} trades, "
            f"P&L: ${summary['total_pnl']:.2f}, "
            f"Win Rate: {summary['win_rate']:.1f}%"
        )

    def clear_trades(self):
        """Clear all logged trades"""
        self.trades = []
        self.trade_count = 0
        logger.info("Trade log cleared")

    def get_trades(self) -> List[Dict[str, Any]]:
        """Get all logged trades"""
        return self.trades

    async def save_trades_to_db(self, db, backtest_id: str) -> bool:
        """Save trades to database"""
        try:
            if self.trades:
                # Add backtest_id to each trade
                trades_with_backtest_id = [
                    {**trade, "backtest_id": backtest_id} for trade in self.trades
                ]

                # Insert trades into database
                result = await run_db_operation(
                    db.trades.insert_many, trades_with_backtest_id
                )
                logger.info(f"Saved {len(result.inserted_ids)} trades to database")
                return True
            return False
        except Exception as e:
            logger.error(f"Error saving trades to database: {e}")
            return False
