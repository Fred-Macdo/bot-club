from celery import Celery
from datetime import datetime, timezone
from typing import Dict, Any
from bson import ObjectId
import asyncio
import logging

# Use absolute imports instead of relative imports
from ..config import *
from ..models.backtest import BacktestStatus
from ..services.data_retrieval.data_manager import DataManager
from ..utils.strategy_executor import StrategyExecutor
from ..database.client import get_db
from ..utils.db_executor import run_db_operation

logger = logging.getLogger(__name__)

# Import the celery app from the main celery module
from src.celery_app import celery_app


# ==================== ASYNC HELPERS ====================

async def _save_backtest_results(
    backtest_id: str,
    user_id: str,
    payload: Dict[str, Any],
    portfolio
) -> None:
    """
    Save backtest results to MongoDB asynchronously.
    Maps StrategyPortfolio fields to the Backtest document format.
    """
    db = get_db()
    collection = db["backtests"]

    # --- Map completed trades to TradeDetail format ---
    trades = []
    for i, trade in enumerate(portfolio.completed_trades):
        trades.append({
            "id": i + 1,
            "position_id": trade.lot_id,
            "symbol": trade.symbol,
            "side": trade.trade_type.value if hasattr(trade.trade_type, 'value') else str(trade.trade_type),
            "entry_date": trade.entry_time.isoformat(),
            "entry_price": float(trade.entry_price),
            "exit_date": trade.exit_time.isoformat() if trade.exit_time else None,
            "exit_price": float(trade.exit_price) if trade.exit_price else None,
            "quantity": float(trade.quantity),
            "pnl": float(trade.realized_pnl),
            "return_pct": trade.realized_pnl_pct or 0.0,
        })

    # --- Map equity curve to EquityPoint format ---
    equity_curve = []
    for snapshot in portfolio.equity_curve:
        equity_curve.append({
            "timestamp": snapshot.timestamp.isoformat(),
            "value": float(snapshot.total_value),
            "cash": float(snapshot.cash),
            "positions_value": float(snapshot.positions_value),
        })

    # --- Calculate derived metrics ---
    final_equity = (
        float(portfolio.equity_curve[-1].total_value)
        if portfolio.equity_curve
        else float(portfolio.current_cash)
    )

    winning_pnl = sum(float(t.realized_pnl) for t in portfolio.completed_trades if t.realized_pnl > 0)
    losing_pnl = abs(sum(float(t.realized_pnl) for t in portfolio.completed_trades if t.realized_pnl < 0))
    profit_factor = round(winning_pnl / losing_pnl, 4) if losing_pnl > 0 else 0.0

    perf = portfolio.performance
    stats = {
        "initial_capital": float(portfolio.initial_capital),
        "final_equity": final_equity,
        "total_return": perf.total_pnl_pct,
        "total_trades": perf.total_trades,
        "winning_trades": perf.winning_trades,
        "losing_trades": perf.losing_trades,
        "win_rate": perf.win_rate,
        "max_drawdown": perf.max_drawdown or 0.0,
        "sharpe_ratio": perf.sharpe_ratio or 0.0,
        "profit_factor": profit_factor,
        "avg_win": float(perf.avg_win) if perf.avg_win else None,
        "avg_loss": float(perf.avg_loss) if perf.avg_loss else None,
    }

    # --- Build the backtest document ---
    # Convert date/datetime objects to ISO strings for MongoDB compatibility
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if hasattr(start_date, 'isoformat'):
        start_date = start_date.isoformat()
    if hasattr(end_date, 'isoformat'):
        end_date = end_date.isoformat()

    backtest_doc = {
        "user_id": user_id,
        "strategy_id": payload.get("strategy_id"),
        "initial_capital": payload.get("initial_capital"),
        "timeframe": payload.get("timeframe", "1d"),
        "start_date": start_date,
        "end_date": end_date,
        "data_provider": payload.get("data_provider", "alpaca"),
        "stats": stats,
        "trades": trades,
        "equity_curve": equity_curve,
        "status": "completed",
        "completed_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }

    await run_db_operation(
        collection.update_one,
        {"backtest_id": backtest_id},
        {
            "$set": backtest_doc,
            "$setOnInsert": {"backtest_id": backtest_id, "created_at": datetime.now(tz=timezone.utc)},
        },
        upsert=True,
    )
    logger.info(f"Saved backtest results to database: {backtest_id}")


async def _save_backtest_error(backtest_id: str, user_id: str, error: str) -> None:
    """Save backtest failure status to MongoDB."""
    db = get_db()
    collection = db["backtest"]

    await run_db_operation(
        collection.update_one,
        {"backtest_id": backtest_id},
        {
            "$set": {
                "user_id": user_id,
                "status": "failed",
                "error": error,
                "updated_at": datetime.now(tz=timezone.utc),
            },
            "$setOnInsert": {"backtest_id": backtest_id, "created_at": datetime.now(tz=timezone.utc)},
        },
        upsert=True,
    )
    logger.info(f"Saved backtest error to database: {backtest_id}")


async def _run_backtest_pipeline(payload: Dict[str, Any]):
    """
    Full async pipeline: fetch data → execute strategy → save results.
    All async operations share a single event loop.
    """
    backtest_id = str(payload["backtest_id"])
    user_id = str(payload["user_id"])

    # 1. Fetch market data
    data_manager = DataManager(
        keys=payload.get("encrypted_keys", {}),
        provider_name=payload.get("data_provider", "alpaca"),
    )
    config = payload["strategy_config"].get("config", payload["strategy_config"])

    # Use dates from the payload (set at backtest runtime), NOT from strategy config
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if hasattr(start_date, 'isoformat'):
        start_date = start_date.isoformat()
    if hasattr(end_date, 'isoformat'):
        end_date = end_date.isoformat()

    data = await data_manager.fetch_historical_data(
        symbols=config.get("symbols", []),
        start_date=start_date,
        end_date=end_date,
        timeframe=payload.get("timeframe", config.get("timeframe", "1d")),
    )
    logger.info(f"Fetched data: {data.shape}")

    # 2. Execute strategy (pass pre-fetched data so executor skips re-fetch)
    executor = StrategyExecutor(
        strategy=payload["strategy_config"],
        data=data,
        initial_capital=payload["initial_capital"],
        encrypted_keys=payload.get("encrypted_keys", {}),
        data_provider=payload.get("data_provider", "alpaca"),
    )
    portfolio = await executor.execute_strategy()

    # 3. Save results to database
    await _save_backtest_results(backtest_id, user_id, payload, portfolio)

    return portfolio


# ==================== CELERY TASK ====================

@celery_app.task(
    bind=True,
    name="src.tasks.backtest_task.run_backtest_task",
    soft_time_limit=900,
    time_limit=960,
    autoretry_for=(ConnectionError, OSError),
    retry_kwargs={"max_retries": 2, "countdown": 30},
)
def run_backtest_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task to execute a backtest.
    
    Args:
        payload: Dict containing:
            - backtest_id: str
            - user_id: str
            - strategy_id: str
            - strategy_config: dict
            - initial_capital: float
            - start_date: str
            - end_date: str
            - data_provider: str
            - timeframe: str
            - encrypted_keys: dict
    
    Returns:
        Dict with backtest results or error
    """
    backtest_id = str(payload["backtest_id"])

    try:
        logger.info(f"Starting backtest task: {backtest_id}")
        logger.info(f"Strategy Config: {payload['strategy_config']}")

        # Run the full async pipeline (fetch → execute → save) in one event loop
        portfolio = asyncio.run(_run_backtest_pipeline(payload))

        logger.info(f"Backtest completed and saved: {backtest_id}")

        return {
            "status": "success",
            "backtest_id": backtest_id,
        }

    except Exception as e:
        logger.error(f"Backtest failed: {backtest_id}, error: {e}")

        # Persist error status so the UI can show the failure
        try:
            asyncio.run(_save_backtest_error(
                backtest_id, payload.get("user_id", ""), str(e)
            ))
        except Exception as save_err:
            logger.error(f"Failed to save error status: {save_err}")

        return {
            "status": "failed",
            "backtest_id": backtest_id,
            "error": str(e),
        }
