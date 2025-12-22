from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health")
async def health_check(request: Request):
    app_state = request.app.state
    return {
        "status": "healthy",
        "services": {
            "db": "connected" if app_state.db_client else "disconnected",
            "backtest": "running" if app_state.backtest_service else "stopped",
            "trading": "running" if app_state.trading_service else "stopped"
        }
    }
