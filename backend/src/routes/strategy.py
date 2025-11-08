from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pymongo.database import Database
from bson import ObjectId

from ..dependencies import get_db, get_current_user_from_token
from ..models.user import UserInDB
from ..models.strategy import (
    Strategy,
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    BacktestParams,
    BacktestResponse,
    BacktestResult
)
from ..crud.strategy import (
    get_strategies_by_user_id,
    get_strategy_by_id,
    create_strategy,
    update_strategy,
    delete_strategy,
    toggle_strategy_status,
    save_backtest_result,
    get_backtest_results_by_strategy,
    get_backtest_result_by_id,
    delete_backtest_results_by_strategy,
    get_default_strategies_from_db
)
from ..services.default_strategies import get_default_strategies_from_db
from ..utils.mongo_helpers import PyObjectId

router = APIRouter()

def strategy_to_response(strategy: Strategy) -> StrategyResponse:
    """Convert Strategy model to response model"""
    return StrategyResponse(
        id=str(strategy.id),
        user_id=str(strategy.user_id),
        name=strategy.name,
        description=strategy.description,
        config=strategy.config,
        is_active=strategy.is_active,
        is_paper=strategy.is_paper,
        performance_stats=strategy.performance_stats,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at
    )

def backtest_result_to_response(backtest_result: BacktestResult) -> BacktestResponse:
    """Convert BacktestResult model to response model"""
    return BacktestResponse(
        id=str(backtest_result.id),
        strategy_id=str(backtest_result.strategy_id),
        total_return=backtest_result.total_return,
        sharpe_ratio=backtest_result.sharpe_ratio,
        max_drawdown=backtest_result.max_drawdown,
        win_rate=backtest_result.win_rate,
        total_trades=backtest_result.total_trades,
        profit_factor=backtest_result.profit_factor,
        initial_capital=backtest_result.initial_capital,
        final_capital=backtest_result.final_capital,
        start_date=backtest_result.start_date,
        end_date=backtest_result.end_date,
        timeframe=backtest_result.timeframe,
        trades=backtest_result.trades,
        equity_curve=backtest_result.equity_curve,
        created_at=backtest_result.created_at
    )

@router.get("/user_strategies", response_model=List[StrategyResponse])
async def get_user_strategies(
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Get all strategies for the current user"""
    try:
        print(f"DEBUG: Fetching strategies for user_id: {current_user.id}")
        print(f"DEBUG: User email: {current_user.email}")
        
        if type(current_user.id) == str:
            strategies = await get_strategies_by_user_id(db, ObjectId(current_user.id))
        else:
            strategies = await get_strategies_by_user_id(db, current_user.id)
        print(f"DEBUG: Found {len(strategies)} strategies in database for user {current_user.id}")
        for strategy in strategies:
            print(f"DEBUG: Strategy - ID: {strategy.id}, Name: {strategy.name}, User ID: {strategy.user_id}")
        
        result = [strategy_to_response(strategy) for strategy in strategies]
        print(f"DEBUG: Returning {len(result)} strategies to frontend")
        
        return result
    except Exception as e:
        print(f"DEBUG: Error fetching strategies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch strategies: {str(e)}"
        )

@router.get("/default", response_model=List[StrategyCreate])
async def get_default_strategies_endpoint(db: Database = Depends(get_db)):
    """Get default strategies from database collection"""
    try:
        strategy_docs = await get_default_strategies_from_db(db)
        
        # Convert raw documents to StrategyCreate format for response
        strategy_creates = []
        for doc in strategy_docs:
            # Create a proper config with all required fields
            raw_config = doc.get("config", {})
            
            # If config is empty, construct it from document root level
            if not raw_config or not raw_config.get("symbols"):
                config_data = {
                    "symbols": doc.get("symbols", ["AAPL"]),
                    "timeframe": doc.get("timeframe", "1d"),
                    "start_date": doc.get("start_date", "2024-01-01"),
                    "end_date": doc.get("end_date", "2024-12-31"),
                    "entry_conditions": doc.get("entry_conditions", []),
                    "exit_conditions": doc.get("exit_conditions", []),
                    "risk_management": doc.get("risk_management", {}),
                    "indicators": doc.get("indicators", [])
                }
            else:
                config_data = raw_config
            
            strategy_creates.append(StrategyCreate(
                name=doc["name"],
                description=doc.get("description", ""),
                config=config_data
            ))
        return strategy_creates
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load default strategies: {str(e)}"
        )

# ...existing code...

@router.get("/defaults/with-ids", response_model=List[dict])
async def get_default_strategies_with_ids(db: Database = Depends(get_db)):
    """Get default strategies with IDs for backtest selection"""
    try:
        default_strategies_collection = db["default_strategies"]
        strategies = []
        
        async for strategy in default_strategies_collection.find({}):
            # Include the _id for backtest purposes
            strategies.append({
                "id": str(strategy["_id"]),
                "name": strategy["name"],
                "description": strategy.get("description", ""),
                "type": "default"
            })
        
        return strategies
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load default strategies with IDs: {str(e)}"
        )

@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Get a specific strategy by ID"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    strategy = await get_strategy_by_id(db, strategy_obj_id, current_user.id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    return strategy_to_response(strategy)

@router.post("/", response_model=StrategyResponse)
async def create_new_strategy(
    strategy_data: StrategyCreate,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Create a new strategy"""
    try:
        strategy = await create_strategy(db, strategy_data, current_user.id)
        return strategy_to_response(strategy)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create strategy: {str(e)}"
        )

@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_existing_strategy(
    strategy_id: str,
    strategy_update: StrategyUpdate,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Update an existing strategy"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    updated_strategy = await update_strategy(db, strategy_obj_id, strategy_update, current_user.id)
    if not updated_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or no changes made"
        )
    
    return strategy_to_response(updated_strategy)

@router.delete("/{strategy_id}")
async def delete_existing_strategy(
    strategy_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Delete a strategy and its associated backtest results"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    # Verify strategy exists and belongs to user
    strategy = await get_strategy_by_id(db, strategy_obj_id, current_user.id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    # Delete associated backtest results first
    await delete_backtest_results_by_strategy(db, strategy_obj_id)
    
    # Delete the strategy
    deleted = await delete_strategy(db, strategy_obj_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete strategy"
        )
    
    return {"message": "Strategy deleted successfully"}

@router.post("/{strategy_id}/toggle", response_model=StrategyResponse)
async def toggle_strategy_trading(
    strategy_id: str,
    toggle_data: dict,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Toggle strategy active/inactive status"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    is_active = toggle_data.get("is_active", False)
    
    updated_strategy = await toggle_strategy_status(db, strategy_obj_id, current_user.id, is_active)
    if not updated_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    return strategy_to_response(updated_strategy)

# Background task for running backtests
async def run_backtest_task(
    db: Database,
    strategy: Strategy,
    params: BacktestParams,
    user_id: str
):
    """Background task to run backtest via backend_services"""
    try:
        from ..services.backtest_client import BacktestServiceClient
        
        # Create client for backend_services
        backtest_client = BacktestServiceClient()
        
        # Start backtest on backend_services
        execution_id = await backtest_client.start_backtest(strategy, params, user_id)
        
        if execution_id:
            print(f"Backtest started on backend_services with execution ID: {execution_id}")
        else:
            print(f"Failed to start backtest for strategy {strategy.id}")
            
    except Exception as e:
        print(f"Backtest failed for strategy {strategy.id}: {str(e)}")

@router.post("/{strategy_id}/backtest", response_model=dict)
async def start_backtest(
    strategy_id: str,
    backtest_params: BacktestParams,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Start a backtest for a strategy"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    # Verify strategy exists and belongs to user
    strategy = await get_strategy_by_id(db, strategy_obj_id, current_user.id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    # Start backtest as background task
    background_tasks.add_task(run_backtest_task, db, strategy, backtest_params, current_user.id)
    
    return {
        "message": "Backtest started",
        "strategy_id": strategy_id,
        "status": "running"
    }

@router.get("/{strategy_id}/backtest", response_model=List[BacktestResponse])
async def get_strategy_backtest_results(
    strategy_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Get all backtest results for a strategy"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid strategy ID format"
        )
    
    # Verify strategy exists and belongs to user
    strategy = await get_strategy_by_id(db, strategy_obj_id, current_user.id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    backtest_results = await get_backtest_results_by_strategy(db, strategy_obj_id)
    return [backtest_result_to_response(result) for result in backtest_results]

@router.get("/{strategy_id}/backtest/{backtest_id}", response_model=BacktestResponse)
async def get_specific_backtest_result(
    strategy_id: str,
    backtest_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Get a specific backtest result"""
    try:
        strategy_obj_id = PyObjectId(strategy_id)
        backtest_obj_id = PyObjectId(backtest_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format"
        )
    
    # Verify strategy exists and belongs to user
    strategy = await get_strategy_by_id(db, strategy_obj_id, current_user.id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )
    
    backtest_result = await get_backtest_result_by_id(db, backtest_obj_id)
    if not backtest_result or backtest_result.strategy_id != strategy_obj_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found"
        )
    
    return backtest_result_to_response(backtest_result)
