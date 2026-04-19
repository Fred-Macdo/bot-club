from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query  # , status
from pydantic import BaseModel
from typing import Literal, Optional

from ..dependencies import get_current_user_from_token, get_db
from ..models.user import User
from ..models.strategy import AccountTypeEnum  # , Strategy, StatusEnum
from ..models.trading_session import TradingSessionStatus
from ..utils.asset_classifier import classify_asset_type, is_within_market_hours
import logging
from ..tasks.trading_tasks import run_live_strategy, stop_live_strategy
from ..celery_app import celery_app
from pymongo.database import Database
from bson import ObjectId

logger = logging.getLogger(__name__)

# Timeframe string → expected iteration interval in seconds
_TIMEFRAME_SECONDS = {
    "1M": 60,
    "5M": 300,
    "15M": 900,
    "30M": 1800,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
}


def _compute_session_health(session: dict) -> str:
    """Return 'active', 'stale', or 'unknown' based on last_iteration_at vs timeframe."""
    last_iter = session.get("last_iteration_at")
    if not last_iter:
        # No iterations yet — check if session is very new (< 5 min since start)
        started = session.get("started_at")
        if started:
            started_dt = (
                datetime.fromisoformat(started) if isinstance(started, str) else started
            )
            if (datetime.now(tz=timezone.utc) - started_dt).total_seconds() < 300:
                return "starting"
        return "unknown"

    if isinstance(last_iter, str):
        last_iter = datetime.fromisoformat(last_iter)
    if last_iter.tzinfo is None:
        last_iter = last_iter.replace(tzinfo=timezone.utc)

    tf = (session.get("config") or {}).get("timeframe", "15M")
    interval = _TIMEFRAME_SECONDS.get(tf.upper(), 900)
    # Stale if no iteration in 3× the expected interval
    threshold = timedelta(seconds=interval * 3)
    if (datetime.now(tz=timezone.utc) - last_iter) > threshold:
        return "stale"
    return "active"


router = APIRouter()


class TradingRequest(BaseModel):
    strategy_id: str
    mode: Literal[AccountTypeEnum.LIVE, AccountTypeEnum.PAPER]
    data_provider: Literal["yahoo", "alpaca", "polygon"]
    initial_capital: float = 1000.0
    extended_hours: bool = False


@router.post("/run")
async def start_trading(
    trading_request: TradingRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """
    Starts live or paper trading for a given strategy.
    Crypto strategies launch a continuous Celery task.
    Stock strategies create a RedBeat cron entry for market-hours scheduling
    and optionally start an immediate task if the market is currently open.
    """
    logger.info(f"Received trading start request: {trading_request}")
    logger.info(f"Current user: {current_user.id} - {current_user.email}")

    user_id = str(current_user.id)
    strategy_id = trading_request.strategy_id

    # ---- Fetch strategy to determine asset type ----
    strategy_doc = db.strategy.find_one({"_id": ObjectId(strategy_id)})
    if not strategy_doc:
        strategy_doc = db.default_strategies.find_one({"_id": ObjectId(strategy_id)})
    if not strategy_doc:
        raise HTTPException(status_code=404, detail="Strategy not found")

    symbols = strategy_doc.get("config", {}).get("symbols", [])
    try:
        asset_type = classify_asset_type(symbols)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    request_dict = trading_request.model_dump(mode="json")
    user_dict = current_user.model_dump(mode="json")

    if asset_type == "crypto":
        # ---- Crypto: launch continuous task immediately ----
        task_result = run_live_strategy.delay(
            trading_request=request_dict,
            current_user=user_dict,
        )
        return {"task_id": task_result.id, "asset_type": "crypto"}

    # ---- Stock: create RedBeat cron schedule ----
    from redbeat import RedBeatSchedulerEntry
    from celery.schedules import crontab

    mode = trading_request.mode
    extended = trading_request.extended_hours
    schedule_name = f"redbeat:stock:{user_id}:{strategy_id}:{mode}"

    if extended:
        cron = crontab(minute="0", hour="4", day_of_week="mon-fri")
    else:
        cron = crontab(minute="30", hour="9", day_of_week="mon-fri")

    entry = RedBeatSchedulerEntry(
        name=schedule_name,
        task="src.tasks.trading_tasks.run_live_strategy",
        schedule=cron,
        kwargs={"trading_request": request_dict, "current_user": user_dict},
        app=celery_app,
    )
    entry.save()
    logger.info(f"Created RedBeat schedule: {schedule_name}")

    # If market is open right now, also fire the task immediately
    task_id = None
    if is_within_market_hours(extended=extended):
        task_result = run_live_strategy.delay(
            trading_request=request_dict,
            current_user=user_dict,
        )
        task_id = task_result.id
        logger.info(f"Market open — also started immediate task {task_id}")

    return {
        "task_id": task_id,
        "asset_type": "stock",
        "schedule_name": schedule_name,
    }


class StopTradingRequest(BaseModel):
    strategy_id: str
    task_id: Optional[str] = None  # May be None for scheduled stock strategies


@router.post("/stop")
async def stop_trading(
    trading_request: StopTradingRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """
    Stops a running live or paper trading strategy.
    For stock strategies, also removes the RedBeat schedule entry.
    """
    logger.info(f"Received trading stop request for task: {trading_request.task_id}")

    user_id = str(current_user.id)

    # Look up the session to find schedule_name (for stock strategies)
    session_doc = db.trading_sessions.find_one(
        {
            "strategy_id": trading_request.strategy_id,
            "user_id": user_id,
        }
    )
    schedule_name = None
    if session_doc:
        schedule_name = (session_doc.get("config") or {}).get("schedule_name")

    # Delete RedBeat entry if it exists
    if schedule_name:
        try:
            from redbeat import RedBeatSchedulerEntry

            entry = RedBeatSchedulerEntry.from_key(schedule_name, app=celery_app)
            entry.delete()
            logger.info(f"Deleted RedBeat schedule: {schedule_name}")
        except Exception as e:
            logger.warning(f"Could not delete RedBeat entry {schedule_name}: {e}")

    # Revoke the running task (if any)
    if trading_request.task_id:
        stop_live_strategy.delay(task_id=trading_request.task_id)

    # If no task running but session is SCHEDULED, mark it STOPPED directly
    if not trading_request.task_id and session_doc:
        db.trading_sessions.update_one(
            {"strategy_id": trading_request.strategy_id, "user_id": user_id},
            {
                "$set": {
                    "status": TradingSessionStatus.STOPPED,
                    "stopped_at": datetime.now(tz=timezone.utc),
                    "updated_at": datetime.now(tz=timezone.utc),
                }
            },
        )

    return {"status": "stop_requested", "task_id": trading_request.task_id}


# ==================== SESSION ENDPOINTS ====================


@router.get("/active")
async def get_active_sessions(
    current_user: User = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """
    Returns all active trading sessions for the authenticated user.
    Called by the frontend on login to restore deployment state.
    """
    try:
        user_id = str(current_user.id)
        active_statuses = [
            TradingSessionStatus.ACTIVE,
            TradingSessionStatus.PENDING,
            TradingSessionStatus.SCHEDULED,
        ]
        sessions = list(
            db.trading_sessions.find(
                {"user_id": user_id, "status": {"$in": active_statuses}},
                {"_id": 0},  # Exclude MongoDB _id
            )
        )

        # Convert datetime objects for JSON serialization
        for session in sessions:
            for key in (
                "created_at",
                "started_at",
                "stopped_at",
                "last_iteration_at",
                "updated_at",
            ):
                if session.get(key) and hasattr(session[key], "isoformat"):
                    session[key] = session[key].isoformat()

            # Staleness check: if last_iteration_at is too old relative to timeframe, mark stale
            # SCHEDULED sessions are healthy — just waiting for next market open
            if session.get("status") == TradingSessionStatus.SCHEDULED:
                session["health"] = "scheduled"
            else:
                session["health"] = _compute_session_health(session)

        logger.info(f"Found {len(sessions)} active sessions for user {user_id}")
        return {"active_sessions": sessions}

    except Exception as e:
        logger.error(f"Error fetching active sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{strategy_id}")
async def get_session_details(
    strategy_id: str,
    mode: Optional[str] = Query(None, description="Trading mode: 'paper' or 'live'"),
    current_user: User = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """
    Returns the trading session details for a specific strategy, including
    the saved portfolio state for resumption. Scoped to the authenticated user.
    """
    try:
        user_id = str(current_user.id)
        query = {"strategy_id": strategy_id, "user_id": user_id}
        if mode:
            query["config.mode"] = mode

        # Get the most recent session
        session = db.trading_sessions.find_one(
            query,
            {"_id": 0},
            sort=[("created_at", -1)],
        )

        if not session:
            raise HTTPException(
                status_code=404, detail="No session found for this strategy"
            )

        # Convert datetime objects
        for key in (
            "created_at",
            "started_at",
            "stopped_at",
            "last_iteration_at",
            "updated_at",
        ):
            if session.get(key) and hasattr(session[key], "isoformat"):
                session[key] = session[key].isoformat()

        # Determine mode from session config if not provided in query
        effective_mode = mode or (session.get("config") or {}).get("mode")

        # Also load the portfolio state if available (scoped by mode)
        portfolio_query = {"strategy_id": strategy_id, "user_id": user_id}
        if effective_mode:
            portfolio_query["mode"] = effective_mode
        portfolio = db.strategy_portfolios.find_one(
            portfolio_query,
            {"_id": 0},
        )

        if portfolio:
            # Clean up any non-serializable fields
            for key in list(portfolio.keys()):
                if hasattr(portfolio.get(key), "isoformat"):
                    portfolio[key] = portfolio[key].isoformat()
            session["portfolio"] = portfolio

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
