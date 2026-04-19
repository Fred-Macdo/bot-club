import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from ..models.backtest import BacktestDetailedSummary

logger = logging.getLogger(__name__)


class PerformanceCalculator:
    """Calculates performance metrics and creates BacktestResult objects"""

    def create_backtest_result(
        self,
        strategy_id: str,
        user_id: str,
        trades: List[Dict[str, Any]],
        initial_capital: float,
        start_date: str,
        end_date: str,
        timeframe: str,
        equity_curve: Optional[List[Dict[str, Any]]] = None,
    ) -> BacktestDetailedSummary:
        """Create a BacktestResult object with calculated performance metrics"""

        # Calculate performance metrics
        metrics = self.calculate_performance_metrics(trades, initial_capital)

        # Calculate final capital
        total_pnl = metrics["total_pnl"]
        final_capital = initial_capital + total_pnl

        # Add emoji to metrics
        total_pnl_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"
        metrics["total_pnl_emoji"] = total_pnl_emoji

        # Create equity curve if not provided
        if equity_curve is None:
            equity_curve = self._generate_equity_curve(trades, initial_capital)

        # Format trades with 2 decimal precision
        formatted_trades = []
        for trade in trades:
            formatted_trade = trade.copy()
            # Round all numeric fields to 2 decimal places
            for key in [
                "entry_price",
                "exit_price",
                "quantity",
                "pnl",
                "pnl_pct",
                "return_pct",
            ]:
                if key in formatted_trade and formatted_trade[key] is not None:
                    formatted_trade[key] = round(float(formatted_trade[key]), 2)
            formatted_trades.append(formatted_trade)

        # Transform equity curve to column-oriented format for frontend
        formatted_equity_curve = {
            "timestamps": [],
            "values": [],
            "cash": [],
            "positions_value": [],
        }

        # Sort by time to ensure chronological order
        equity_curve.sort(key=lambda x: x.get("time") or x.get("date"))

        for point in equity_curve:
            formatted_equity_curve["timestamps"].append(
                point.get("time") or point.get("date")
            )
            formatted_equity_curve["values"].append(
                round(float(point.get("equity", 0)), 2)
            )
            formatted_equity_curve["cash"].append(round(float(point.get("cash", 0)), 2))
            formatted_equity_curve["positions_value"].append(
                round(float(point.get("positions_value", 0)), 2)
            )

        return BacktestDetailedSummary(
            strategy_id=strategy_id,
            user_id=user_id,
            total_return=round(metrics["total_return"], 2),
            sharpe_ratio=round(metrics["sharpe_ratio"], 2),
            max_drawdown=round(metrics["max_drawdown"], 2),
            win_rate=round(metrics["win_rate"], 2),
            total_trades=metrics["total_trades"],  # Keep as integer
            profit_factor=round(metrics["profit_factor"], 2),
            initial_capital=round(initial_capital, 2),
            final_capital=round(final_capital, 2),
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            trades=formatted_trades,
            equity_curve=formatted_equity_curve,
        )

    def _generate_equity_curve(
        self, trades: List[Dict], initial_capital: float
    ) -> List[Dict[str, Any]]:
        """Generate equity curve data from trades"""
        if not trades:
            return [
                {
                    "date": datetime.now(tz=timezone.utc).isoformat(),
                    "equity": round(initial_capital, 2),
                }
            ]

        df = pd.DataFrame(trades)

        # Sort by exit time
        df = df.sort_values("exit_time")

        # Calculate cumulative P&L
        cumulative_pnl = df["pnl"].cumsum()
        equity_values = initial_capital + cumulative_pnl

        # Create equity curve
        equity_curve = []
        for i, (_, row) in enumerate(df.iterrows()):
            equity_curve.append(
                {
                    "date": row["exit_time"].isoformat(),
                    "equity": round(float(equity_values.iloc[i]), 2),
                    "trade_pnl": round(float(row["pnl"]), 2),
                }
            )

        return equity_curve

    def calculate_performance_metrics(
        self, trades: List[Dict], initial_capital: float = 100000.0
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        if not trades:
            return self._empty_performance_metrics()

        # Convert trades to DataFrame for easier calculations
        df = pd.DataFrame(trades)

        # Basic metrics
        total_trades = len(trades)
        winning_trades = len(df[df["pnl"] > 0])
        losing_trades = len(df[df["pnl"] < 0])

        # Calculate returns
        total_pnl = df["pnl"].sum()
        total_return = (total_pnl / initial_capital) * 100

        # Win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Average trade metrics
        avg_win = df[df["pnl"] > 0]["pnl"].mean() if winning_trades > 0 else 0
        avg_loss = df[df["pnl"] < 0]["pnl"].mean() if losing_trades > 0 else 0
        avg_trade = df["pnl"].mean()

        # Risk metrics
        max_drawdown = self._calculate_max_drawdown(df, initial_capital)
        sharpe_ratio = self._calculate_sharpe_ratio(df)

        # Profit factor - use 999.99 instead of float('inf') for JSON compatibility
        gross_profit = df[df["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(df[df["pnl"] < 0]["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.99

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return": round(total_return, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_trade": round(avg_trade, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "profit_factor": round(profit_factor, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
        }

    def _calculate_max_drawdown(
        self, df: pd.DataFrame, initial_capital: float
    ) -> float:
        """Calculate maximum drawdown"""
        if df.empty:
            return 0.0

        # Calculate cumulative equity curve
        cumulative_pnl = df["pnl"].cumsum()
        equity_curve = initial_capital + cumulative_pnl

        # Calculate running maximum
        running_max = equity_curve.expanding().max()

        # Calculate drawdown
        drawdown = (equity_curve - running_max) / running_max * 100

        return abs(drawdown.min())

    def _calculate_sharpe_ratio(
        self, df: pd.DataFrame, risk_free_rate: float = 0.02
    ) -> float:
        """Calculate Sharpe ratio"""
        if df.empty or len(df) < 2:
            return 0.0

        # Calculate daily returns
        daily_returns = df.groupby(df["exit_time"].dt.date)["pnl"].sum()

        if len(daily_returns) < 2:
            return 0.0

        # Calculate Sharpe ratio
        excess_returns = daily_returns - (risk_free_rate / 252)  # Daily risk-free rate
        sharpe = (
            np.sqrt(252) * (excess_returns.mean() / excess_returns.std())
            if excess_returns.std() > 0
            else 0
        )

        return sharpe

    def _empty_performance_metrics(self) -> Dict[str, Any]:
        """Return empty performance metrics when no trades exist"""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "total_return": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_trade": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "profit_factor": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
        }

    def calculate_symbol_performance(
        self, trades: List[Dict]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate performance metrics per symbol"""
        if not trades:
            return {}

        df = pd.DataFrame(trades)
        symbol_metrics = {}

        for symbol in df["symbol"].unique():
            symbol_trades = df[df["symbol"] == symbol]
            symbol_metrics[symbol] = self.calculate_performance_metrics(
                symbol_trades.to_dict("records")
            )

        return symbol_metrics

    def generate_trade_summary(self, trades: List[Dict]) -> Dict[str, Any]:
        """Generate a summary of trades for reporting"""
        if not trades:
            return {"summary": "No trades executed"}

        df = pd.DataFrame(trades)

        # Group by symbol
        symbol_summary = (
            df.groupby("symbol")
            .agg(
                {
                    "pnl": ["count", "sum", "mean"],
                    "entry_price": "mean",
                    "exit_price": "mean",
                }
            )
            .round(2)
        )

        # Flatten column names
        symbol_summary.columns = [
            "trade_count",
            "total_pnl",
            "avg_pnl",
            "avg_entry",
            "avg_exit",
        ]

        return {
            "total_trades": len(trades),
            "symbols_traded": list(df["symbol"].unique()),
            "symbol_performance": symbol_summary.to_dict("index"),
            "date_range": {
                "start": df["entry_time"].min().isoformat(),
                "end": df["exit_time"].max().isoformat(),
            },
        }
