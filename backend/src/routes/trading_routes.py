import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from ..dependencies import get_current_user_from_token
from ..models.user import User
from ..models.strategy import Strategy, AccountTypeEnum, StatusEnum
import logging
from ..tasks.trading_tasks import run_live_strategy, stop_live_strategy
from ..celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()

# This should match the service name and port in your docker-compose.yml    
# Corrected 'backend-services' to 'backend_services'


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