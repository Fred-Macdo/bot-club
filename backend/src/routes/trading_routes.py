import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from ..dependencies import get_current_user_from_token
from ..models.user import User
from ..models.strategy import Strategy, AccountTypeEnum, StatusEnum
import logging
from ..config import BACKEND_SERVICES_URL

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
    try:
        payload = {
            "strategy_id": trading_request.strategy_id,
            "user_id": str(current_user.id),
            "mode": trading_request.mode,
            "data_provider": trading_request.data_provider
        }
        logger.info(f"DEBUG TRADING: Trading request payload: {payload}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{BACKEND_SERVICES_URL}/trading/run", json=payload, timeout=30)
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to communicate with trading service: {e}"
        )

class StopTradingRequest(BaseModel):
    strategy_id: str

@router.post("/stop")
async def stop_trading(
    trading_request: StopTradingRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Stops a running live or paper trading strategy.
    """
    try:
        payload = {
            "strategy_id": trading_request.strategy_id,
            "user_id": str(current_user.id)
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{BACKEND_SERVICES_URL}/trading/stop", json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to communicate with trading service: {e}"
        ) 