import requests
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from ..dependencies import get_current_user_from_token
from ..models.user import User
from ..models.strategy import Strategy
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# This should match the service name and port in your docker-compose.yml
# Corrected 'backend-services' to 'backend_services'
BACKEND_SERVICES_URL = "http://backend_services:8001"

class TradingRequest(BaseModel):
    strategy_id: str
    mode: Literal['live', 'paper']
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
        response = requests.post(f"{BACKEND_SERVICES_URL}/trading/run", json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
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
        response = requests.post(f"{BACKEND_SERVICES_URL}/trading/stop", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to communicate with trading service: {e}"
        ) 