from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from ..dependencies import get_current_user_from_token
from ..models.user import User
from ..models.strategy import Strategy, AccountTypeEnum, StatusEnum
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class TradingRequest(BaseModel):
    strategy_id: str
    mode: Literal[AccountTypeEnum.LIVE, AccountTypeEnum.PAPER]
    data_provider: Literal['yahoo', 'alpaca', 'polygon']

@router.post("/run")
async def start_trading(
    trading_request: TradingRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Starts live or paper trading for a given strategy using CeleryTradingManager directly.
    """
    from ..main import app
    from ..api.celery_trading_manager import celery_trading_manager
    
    try:
        payload = {
            "strategy_id": trading_request.strategy_id,
            "user_id": str(current_user.id),
            "mode": trading_request.mode,
            "data_provider": trading_request.data_provider
        }
        logger.info(f"Starting trading with payload: {payload}")
        
        # Call CeleryTradingManager directly instead of HTTP proxy
        result = await celery_trading_manager.start_trading(
            strategy_id=payload["strategy_id"],
            user_id=payload["user_id"],
            mode=payload["mode"],
            data_provider=payload["data_provider"]
        )
        
        return result
            
    except Exception as e:
        logger.error(f"Failed to start trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start trading: {str(e)}"
        )

class StopTradingRequest(BaseModel):
    strategy_id: str

@router.post("/stop")
async def stop_trading(
    trading_request: StopTradingRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Stops a running live or paper trading strategy using CeleryTradingManager directly.
    """
    from ..api.celery_trading_manager import celery_trading_manager
    
    try:
        payload = {
            "strategy_id": trading_request.strategy_id,
            "user_id": str(current_user.id)
        }
        logger.info(f"Stopping trading with payload: {payload}")
        
        # Call CeleryTradingManager directly instead of HTTP proxy
        result = await celery_trading_manager.stop_trading(
            strategy_id=payload["strategy_id"],
            user_id=payload["user_id"]
        )
        
        return result
            
    except Exception as e:
        logger.error(f"Failed to stop trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop trading: {str(e)}"
        ) 