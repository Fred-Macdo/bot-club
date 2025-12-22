from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging
import json

from models.strategy import Strategy
from models.user_config import ConfigEncryption
from services.utils.enums import TradingMode
from api.celery_trading_manager import celery_trading_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trading")

class TradingRunRequest(BaseModel):
    strategy_id: str
    user_id: str
    mode: str
    data_provider: str
    
    model_config = ConfigDict(extra="allow")

class TradingStopRequest(BaseModel):
    strategy_id: str
    user_id: Optional[str] = None

def json_serial(obj):
    if isinstance(obj, (datetime, ObjectId)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

@router.post("/run")
async def run_trading(request: Request, payload: TradingRunRequest):
    """
    Start a trading strategy.
    """
    try:
        logger.info(f"Received trading request data: {payload}")
        
        strategy_id = payload.strategy_id
        user_id = payload.user_id

        # Fetch strategy from DB
        strategy_doc = await request.app.state.db.strategy.find_one({"_id": ObjectId(strategy_id)})
        if not strategy_doc:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_config = strategy_doc.get("config") or {}

        if celery_trading_manager.is_running(strategy_id):
            raise HTTPException(status_code=400, detail="Strategy is already running")
        
        mode = TradingMode(payload.mode)

        # Get user configuration directly from DB
        user_config_doc = await request.app.state.db.user_config.find_one({"user_id": user_id})
        if not user_config_doc:
            raise HTTPException(status_code=404, detail="User config not found")

        # Decrypt credentials based on mode
        if mode == TradingMode.PAPER:
            api_key = ConfigEncryption.decrypt_value(user_config_doc.get("alpaca_paper_api_key"))
            secret_key = ConfigEncryption.decrypt_value(user_config_doc.get("alpaca_paper_secret_key"))
            paper = True
        else:
            api_key = ConfigEncryption.decrypt_value(user_config_doc.get("alpaca_live_api_key"))
            secret_key = ConfigEncryption.decrypt_value(user_config_doc.get("alpaca_live_secret_key"))
            paper = False

        if not api_key or not secret_key:
            raise HTTPException(status_code=400, detail="Alpaca API key/secret not configured for the selected mode")

        alpaca_config = {
            "API_KEY": api_key,
            "API_SECRET": secret_key,
            "PAPER": paper,
        }
        
        # Start the strategy task (do NOT await; start_strategy is sync)
        success = celery_trading_manager.start_strategy(
            strategy_id=strategy_id,
            strategy_config=strategy_config,
            alpaca_config=alpaca_config,
            user_id=user_id
        )

        if not success:
            raise HTTPException(status_code=400, detail="Strategy is already running")

        return {"status": "success", "message": "Strategy started successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_trading(request: Request, data: TradingStopRequest):
    app_state = request.app.state
    strategy_id = data.strategy_id
    user_id = data.user_id

    if not user_id:
        strategy = await app_state.db.strategy.find_one({"_id": ObjectId(strategy_id)})
        if strategy:
             user_id = str(strategy.get('user_id'))

    success = await celery_trading_manager.stop_strategy(strategy_id)
    
    if user_id:
        session_id = f"{user_id}_{strategy_id}_session"
        await app_state.db.deployed_strategies.update_one(
            {"session_id": session_id}, 
            {"$set": {"active": False}},
            upsert=True
        )

    if not success:
        raise HTTPException(status_code=404, detail="Trader not running or not found")

    return {"status": "stopped", "strategy_id": strategy_id}

@router.get("/active")
async def get_active_sessions(request: Request, user_id: str = Query(...)):
    app_state = request.app.state
    logger.info(f"Checking for active sessions in deployed_strategies for user {user_id}")
    
    active_sessions_cursor = app_state.db.deployed_strategies.find({
        "user_id": user_id,
        "active": True
    })
    
    active_sessions = []
    
    async for session in active_sessions_cursor:
        strategy_id = session.get("strategy_id")
        strategy = await app_state.db.strategy.find_one({"_id": ObjectId(strategy_id)})
        strategy_name = strategy.get("name", "Unknown Strategy") if strategy else "Unknown Strategy"

        active_sessions.append({
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "active": True,
            "task_id": session.get("task_id"),
            "timestamp": session.get("timestamp"),
            "mode": session.get("mode", "paper"),
            "data_provider": session.get("data_provider", "alpaca")
        })
    
    logger.info(f"Found {len(active_sessions)} active sessions for user {user_id}")
    return {"active_sessions": active_sessions}

@router.get("/session/{strategy_id}")
async def get_session_details(request: Request, strategy_id: str, user_id: Optional[str] = Query(None)):
    app_state = request.app.state
    
    if not user_id:
        strategy = await app_state.db.strategy.find_one({"_id": ObjectId(strategy_id)})
        if strategy:
            user_id = str(strategy.get('user_id'))
    
    if not user_id:
         raise HTTPException(status_code=400, detail="User ID required or strategy not found")

    session_id = f"{user_id}_{strategy_id}_session"
    session = await app_state.db.deployed_strategies.find_one({"session_id": session_id})
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if '_id' in session:
        del session['_id']
    
    # Manual serialization for ObjectId and datetime if needed, 
    # but FastAPI usually handles dicts fine if they don't contain custom types.
    # However, session might contain ObjectId or datetime.
    # We can use json.loads(json.dumps(..., default=json_serial)) to be safe
    return json.loads(json.dumps(session, default=json_serial))

@router.get("/status/{strategy_id}")
async def get_status(strategy_id: str):
    try:
        status = celery_trading_manager.get_status(strategy_id)
        return status
    except Exception as e:
        logger.error(f"Error getting trading status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
