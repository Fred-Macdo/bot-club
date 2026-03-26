import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Literal, Optional

from ..dependencies import get_current_user_from_token, get_db
from ..models.user import User
from ..models.strategy import Strategy, AccountTypeEnum, StatusEnum
from ..models.trading_session import TradingSessionStatus
import logging
from ..tasks.trading_tasks import run_live_strategy, stop_live_strategy
from ..celery_app import celery_app
from pymongo.database import Database

logger = logging.getLogger(__name__)

router = APIRouter()


class TradingRequest(BaseModel):
    strategy_id: str
    mode: Literal[AccountTypeEnum.LIVE, AccountTypeEnum.PAPER]
    data_provider: Literal['yahoo', 'alpaca', 'polygon']
    initial_capital: float = 1000.0

@router.post("/run")
async def start_trading(
    trading_request: TradingRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Starts live or paper trading for a given strategy.
    """
    logger.info(f"Received trading start request: {trading_request}")
    logger.info(f"Current user: {current_user.id} - {current_user.email}")
    # run celery tasks
    task_result = run_live_strategy.delay(trading_request=trading_request.model_dump(mode='json'), 
                                          current_user=current_user.model_dump(mode='json'))
    return {"task_id": task_result.id}


class StopTradingRequest(BaseModel):
    strategy_id: str
    task_id: str

@router.post("/stop")
async def stop_trading(
    trading_request: StopTradingRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Stops a running live or paper trading strategy.
    """
    logger.info(f"Received trading stop request for task: {trading_request.task_id}")
    
    # Call the stop task
    stop_live_strategy.delay(task_id=trading_request.task_id)
    
    return {"status": "stop_requested", "task_id": trading_request.task_id}


# ==================== SESSION ENDPOINTS ====================

@router.get("/active")
async def get_active_sessions(
    user_id: str = Query(..., description="User ID to check active sessions for"),
    db: Database = Depends(get_db),
):
    """
    Returns all active trading sessions for a user.
    Called by the frontend on login to restore deployment state.
    """
    try:
        active_statuses = [TradingSessionStatus.ACTIVE, TradingSessionStatus.PENDING]
        sessions = list(db.trading_sessions.find(
            {"user_id": user_id, "status": {"$in": active_statuses}},
            {"_id": 0},  # Exclude MongoDB _id
        ))

        # Convert datetime objects for JSON serialization
        for session in sessions:
            for key in ("created_at", "started_at", "stopped_at", "last_iteration_at", "updated_at"):
                if session.get(key) and hasattr(session[key], "isoformat"):
                    session[key] = session[key].isoformat()

        logger.info(f"Found {len(sessions)} active sessions for user {user_id}")
        return {"active_sessions": sessions}

    except Exception as e:
        logger.error(f"Error fetching active sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{strategy_id}")
async def get_session_details(
    strategy_id: str,
    user_id: Optional[str] = Query(None, description="Optional user ID filter"),
    db: Database = Depends(get_db),
):
    """
    Returns the trading session details for a specific strategy, including
    the saved portfolio state for resumption.
    """
    try:
        query = {"strategy_id": strategy_id}
        if user_id:
            query["user_id"] = user_id

        # Get the most recent session
        session = db.trading_sessions.find_one(
            query,
            {"_id": 0},
            sort=[("created_at", -1)],
        )

        if not session:
            raise HTTPException(status_code=404, detail="No session found for this strategy")

        # Convert datetime objects
        for key in ("created_at", "started_at", "stopped_at", "last_iteration_at", "updated_at"):
            if session.get(key) and hasattr(session[key], "isoformat"):
                session[key] = session[key].isoformat()

        # Also load the portfolio state if available
        portfolio_query = {"strategy_id": strategy_id}
        if user_id:
            portfolio_query["user_id"] = user_id

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