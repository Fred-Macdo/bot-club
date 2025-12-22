from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any

router = APIRouter(prefix="/backtest")

class BacktestRequest(BaseModel):
    strategy_id: str
    user_id: str
    initial_capital: float
    start_date: str
    end_date: str
    timeframe: str
    
    model_config = ConfigDict(extra="allow")

@router.post("/run")
async def run_backtest(request: Request, data: BacktestRequest):
    app_state = request.app.state
    try:
        backtest_id = await app_state.backtest_service.run_backtest(
            strategy_id=data.strategy_id,
            user_id=data.user_id,
            params=data.model_dump()
        )
        return {"status": "started", "backtest_id": backtest_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{backtest_id}/status")
async def get_status(request: Request, backtest_id: str):
    app_state = request.app.state
    status = await app_state.backtest_service.get_status(backtest_id)
    if not status:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return status

@router.delete("/{backtest_id}")
async def cancel_backtest(request: Request, backtest_id: str):
    app_state = request.app.state
    success = await app_state.backtest_service.cancel_backtest(backtest_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to cancel backtest")
    return {"status": "cancelled"}
