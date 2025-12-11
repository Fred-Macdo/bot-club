# backend/src/routes/backtest_routes.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from pydantic import BaseModel
import uuid
import asyncio
import httpx
from pymongo.database import Database
from bson import ObjectId
import json
import logging
from ..database.client import get_db
from ..models.backtest import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestStatus,
    TradeDetail,
    EquityCurve,
    BacktestMetrics,
    BacktestResultResponse,
    TradeDetailsData,
    TradeDetailsResponse,
    DeployRequest,
    DeployResponse,
    BacktestSummary,
    BacktestDetailedSummary
)
from ..models.strategy import Strategy
from ..models.user import UserInDB
from ..dependencies import get_current_user_from_token
from ..utils.redis_client import redis_client
from ..services.default_strategies import get_default_strategies_from_db
from ..utils.db_executor import run_db_operation

router = APIRouter(tags=["backtest"])
logger = logging.getLogger(__name__)

# Async backtest execution
async def run_backtest_async(
    backtest_id: str,
    user_id: str,
    strategy_config: dict,
    initial_capital: float,
    timeframe: str,
    start_date: str,
    end_date: str,
    data_provider: str,
    db: Database
):
    """Run backtest asynchronously and update progress in Redis"""
    try:
        # Update status to running
        await redis_client.hset(f"backtest:{backtest_id}", mapping={
            "status": "running",
            "progress": 0,
            "user_id": user_id
        })
        
        # Call backend services to run the backtest
        try:
            backend_services_url = "http://backend_services:8001"  # Docker service name
            backtest_payload = {
                "strategy_id": str(strategy_config.get('_id', strategy_config.get('id', ''))),
                "user_id": user_id,
                "initial_capital": initial_capital,
                "start_date": start_date,
                "end_date": end_date,
                "timeframe": timeframe,
                "data_provider": data_provider
            }
            
            print(f"Calling backend_services with payload: {backtest_payload}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{backend_services_url}/backtest/run",
                    json=backtest_payload,
                    timeout=300 # Backtests can take a while
                )
            
            if response.status_code == 200:
                # Backend services will handle the execution
                results = response.json()
                print(f"Backend services response: {results}")
                
                # Update status to completed
                await redis_client.hset(f"backtest:{backtest_id}", mapping={
                    "status": "completed",
                    "progress": 100
                })
            else:
                raise Exception(f"Backend services error: {response.text}")
                
        except httpx.RequestError as e:
            raise Exception(f"Error calling backend_services: {e}")
        except ImportError:
            # Fallback to mock implementation if requests is not available
            print("Warning: requests module not available, using mock implementation")
            
            # Simulate backtest execution
            await asyncio.sleep(1)  # Simulate processing time
            
            
            # Update status to completed
            await redis_client.hset(f"backtest:{backtest_id}", mapping={
                "status": "completed",
                "progress": 100
            })
        
        # Save results to database
        strategy_name = strategy_config.get("name", "Unknown Strategy")
        
        backtest_result_data = {
            "user_id": ObjectId(user_id),
            "strategy_id": ObjectId(strategy_config['_id']),
            "strategy_name": strategy_name,
            "initial_capital": initial_capital,
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": timeframe,
            "data_provider": data_provider,
            "stats": results['stats'],
            "equity_curve": results['equity_curve'],
            "created_at": datetime.utcnow()
        }
        
        insert_result = await run_db_operation(db.backtests.insert_one, backtest_result_data)
        new_backtest_id = insert_result.inserted_id

        # Save trades
        if 'trades' in results and results['trades']:
            trades_to_insert = []
            for trade_data in results['trades']:
                trade_data["backtest_id"] = new_backtest_id
                trades_to_insert.append(trade_data)
            await run_db_operation(db.trades.insert_many, trades_to_insert)
        
        # Update status to completed
        await redis_client.hset(f"backtest:{backtest_id}", mapping={
            "status": "completed",
            "progress": 100
        })
        
        # Set expiry for Redis data (24 hours)
        await redis_client.expire(f"backtest:{backtest_id}", 86400)
        
    except Exception as e:
        # Update status to failed
        await redis_client.hset(f"backtest:{backtest_id}", mapping={
            "status": "failed",
            "error": str(e)
        })
        # Log error
        print(f"Backtest {backtest_id} failed: {str(e)}")

@router.post("/run", response_model=BacktestRunResponse)
async def run_backtest(
    request: BacktestRunRequest,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """
    Starts a new backtest run.

    This endpoint initiates a backtest asynchronously. It validates the request,
    loads the specified strategy, and schedules the backtest to run in the
    background.

    Args:
        request: The backtest run request containing parameters like strategy_id,
                 capital, timeframe, start/end dates, and data provider.
        background_tasks: FastAPI's background tasks manager to run the backtest
                          process asynchronously.
        current_user: The authenticated user initiating the backtest.
        db: The database connection instance.

    Returns:
        A response containing the unique backtest_id and a confirmation message.
    """
    # Validate dates
    try:
        start = datetime.strptime(request.start_date, '%Y-%m-%d')
        end = datetime.strptime(request.end_date, '%Y-%m-%d')
        if start >= end:
            raise ValueError("Start date must be before end date")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Load strategy configuration
    if request.strategy_type == 'default':
        default_strategies = await get_default_strategies_from_db(db)
        logger.info(f"Default strategies: {default_strategies}")
        strategy_config = next((s for s in default_strategies if str(s["_id"]) == request.strategy_id), None)
        if not strategy_config:
            raise HTTPException(status_code=404, detail="Default strategy not found")
    else:
        # Load user strategy from database
        print(
        "current_user: ", current_user.userName, '\n',
        "type: ", type(current_user), '\n',
        "current_user_id", current_user.id, '\n',
        "strategy_id: ", request.strategy_id, '\n',
        "type_strategy_id", type(request.strategy_id)
        )

        strategy = await run_db_operation(db.strategy.find_one, {
            "_id": ObjectId(str(request.strategy_id))
        })

        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_config = strategy
    
    if not strategy_config:
        raise HTTPException(status_code=404, detail="Strategy configuration not found")
    
    # Generate backtest ID
    backtest_id = str(uuid.uuid4())
    
    # Start backtest in background
    background_tasks.add_task(
        run_backtest_async,
        backtest_id,
        str(current_user.id),
        strategy_config,
        request.initial_capital,
        request.timeframe,
        request.start_date,
        request.end_date,
        request.data_provider,
        db
    )
    
    return BacktestRunResponse(
        backtest_id=backtest_id,
        message="Backtest started successfully"
    )

@router.get("/status/{backtest_id}", response_model=BacktestStatus)
async def get_backtest_status(
    backtest_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token)
):
    """
    Retrieves the status of a specific backtest.

    This endpoint polls the status of a backtest run using its ID,
    returning the current state (e.g., running, completed, failed)
    and progress.

    Args:
        backtest_id: The unique identifier of the backtest.
        current_user: The authenticated user who owns the backtest.

    Returns:
        The current status of the backtest, including progress and any errors.
    """
    # Get status from Redis
    data = await redis_client.hgetall(f"backtest:{backtest_id}")
    
    if not data:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    # Verify user owns this backtest
    if data.get('user_id') != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return BacktestStatus(
        status=data.get('status', 'unknown'),
        progress=int(data.get('progress', 0)),
        error=data.get('error')
    )

@router.get("/results/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_results(
    backtest_id: str,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """
    Fetches the detailed results of a completed backtest.

    Args:
        backtest_id: The unique identifier of the backtest.
        current_user: The authenticated user who owns the backtest.
        db: The database connection instance.

    Returns:
        A detailed response containing the backtest results, including
        equity curve, trade list, and performance metrics.
    """
    # Fetch backtest from database
    backtest = await run_db_operation(db.backtests.find_one, {
        "id": backtest_id,
        "user_id": current_user.id
    })
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest results not found")
    
    # Fetch trades
    trades_cursor = db.trades.find({"backtest_id": backtest_id})
    trades = await run_db_operation(list, trades_cursor)
    
    # Get strategy name
    strategy = await run_db_operation(db.strategies.find_one, {"id": backtest["strategy_id"]})
    strategy_name = strategy["name"] if strategy else "Unknown Strategy"
    
    # Format response
    return BacktestResultResponse(
        backtest_id=backtest_id,
        strategy_name=strategy_name,
        equity_curve=EquityCurve(
            timestamps=backtest.equity_curve['dates'],
            values=backtest.equity_curve['total_equity'],
            cash=backtest.equity_curve['cash_balance'],
            positions_value=backtest.equity_curve['invested_capital']
        ),
        trades=[
            TradeDetail(
                id=trade.id,
                symbol=trade.symbol,
                side=trade.side,
                entry_date=trade.entry_date,
                entry_price=trade.entry_price,
                exit_date=trade.exit_date,
                exit_price=trade.exit_price,
                quantity=trade.quantity,
                pnl=trade.pnl,
                return_pct=trade.return_pct
            ) for trade in trades
        ],
        metrics=BacktestMetrics(
            initial_capital=backtest.initial_capital,
            final_equity=backtest.final_equity,
            total_return=backtest.total_return,
            total_trades=backtest.total_trades,
            winning_trades=len([t for t in trades if t.pnl > 0]),
            losing_trades=len([t for t in trades if t.pnl <= 0]),
            win_rate=backtest.win_rate,
            max_drawdown=backtest.max_drawdown,
            sharpe_ratio=backtest.sharpe_ratio,
            profit_factor=backtest.profit_factor
        )
    )

@router.get("/trade-details/{backtest_id}/{trade_id}", response_model=TradeDetailsResponse)
async def get_trade_details(
    backtest_id: str,
    trade_id: int,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """
    Retrieves detailed information for a single trade within a backtest.

    This includes OHLCV data and indicator values around the time the
    trade was executed, providing context for the trading decision.

    Args:
        backtest_id: The identifier of the backtest the trade belongs to.
        trade_id: The identifier of the specific trade.
        current_user: The authenticated user who owns the backtest.
        db: The database connection instance.

    Returns:
        Detailed data for the specified trade, including market data and
        indicators.
    """
    # Verify backtest ownership
    backtest = await run_db_operation(db.backtest_results.find_one, {
        "id": backtest_id,
        "user_id": current_user.id
    })
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    # Get trade
    trade = await run_db_operation(db.trades.find_one, {
        "id": trade_id,
        "backtest_id": backtest_id
    })
    
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Get strategy configuration
    strategy = await run_db_operation(db.strategies.find_one, {"id": backtest["strategy_id"]})
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Initialize mock data provider for now (replace with actual implementation later)
    # This is a placeholder - in a real implementation you'd fetch actual market data
    
    # For now, return mock trade details since data provider isn't implemented
    # TODO: Implement actual market data fetching and indicator calculations
    
    entry_data = [
        TradeDetailsData(
            date=trade.entry_date,
            open=trade.entry_price * 0.99,
            high=trade.entry_price * 1.01,
            low=trade.entry_price * 0.98,
            close=trade.entry_price,
            volume=1000000,
            indicators={"RSI": 50.0, "SMA": trade.entry_price},
            is_signal=True
        )
    ]
    
    exit_data = None
    if trade.exit_date and trade.exit_price:
        exit_data = [
            TradeDetailsData(
                date=trade.exit_date,
                open=trade.exit_price * 0.99,
                high=trade.exit_price * 1.01,
                low=trade.exit_price * 0.98,
                close=trade.exit_price,
                volume=1000000,
                indicators={"RSI": 60.0, "SMA": trade.exit_price},
                is_signal=True
            )
        ]
    
    return TradeDetailsResponse(
        trade=TradeDetail(
            id=trade.id,
            symbol=trade.symbol,
            side=trade.side,
            entry_date=trade.entry_date,
            entry_price=trade.entry_price,
            exit_date=trade.exit_date,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            pnl=trade.pnl,
            return_pct=trade.return_pct
        ),
        entry_data=entry_data,
        exit_data=exit_data
    )

@router.post("/deploy", response_model=DeployResponse)
async def deploy_strategy(
    request: DeployRequest,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """
    Deploys a trading strategy for live or paper trading.

    This endpoint takes a strategy configuration and deploys it, creating a
    record of the deployment and preparing it for execution in the
    specified trading mode.

    Args:
        request: The deployment request, including the strategy ID, trading mode,
                 and initial capital.
        current_user: The authenticated user deploying the strategy.
        db: The database connection instance.

    Returns:
        A confirmation response with the new deployment ID.
    """
    # Load strategy configuration
    if request.strategy_type == 'default':
        default_strategies = await get_default_strategies_from_db(db)
        strategy_config = next((s for s in default_strategies if s["id"] == request.strategy_id), None)
        if not strategy_config:
            raise HTTPException(status_code=404, detail="Default strategy not found")
        strategy_name = strategy_config.get('name', 'Default Strategy')
    else:
        # Load user strategy
        strategy = await run_db_operation(db.strategies.find_one, {
            "id": request.strategy_id.replace('user_', ''),
            "user_id": current_user.id
        })
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_config = strategy.config
        strategy_name = strategy.name
    
    # Create deployment record
    deployment_id = str(uuid.uuid4())
    
    # In a real implementation, you would:
    # 1. Create a deployment record in the database
    # 2. Start the trading bot with the strategy configuration
    # 3. Configure risk management settings
    # 4. Set up monitoring and alerts
    
    # For now, we'll simulate the deployment
    deployment_data = {
        'deployment_id': deployment_id,
        'user_id': current_user.id,
        'strategy_name': strategy_name,
        'strategy_config': strategy_config,
        'mode': request.mode,
        'initial_capital': request.initial_capital,
        'status': 'active',
        'created_at': datetime.utcnow().isoformat()
    }
    
    # Store deployment info in Redis (or database)
    await redis_client.hset(
        f"deployment:{deployment_id}",
        mapping=deployment_data
    )
    
    return DeployResponse(
        success=True,
        deployment_id=deployment_id,
        message=f"Strategy '{strategy_name}' successfully deployed to {request.mode} trading"
    )

# Additional routes for data providers
@router.get("/user/data-providers")
async def get_user_data_providers(
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """
    Fetches the list of available data providers for the authenticated user.

    It checks for configured API keys to determine which data sources
    (e.g., Alpaca, Polygon) are available for the user to select from when
    running a backtest.

    Args:
        current_user: The authenticated user.
        db: The database connection instance.

    Returns:
        A list of available data provider names.
    """
    providers = ['yahoo']  # Yahoo is always available
    
    # Check for configured API keys
    user_config = await run_db_operation(db.user_configs.find_one, {
        "user_id": current_user.id
    })
    
    if user_config:
        if user_config.get("alpaca_api_key") and user_config.get("alpaca_secret_key"):
            providers.append('alpaca')
        if user_config.get("polygon_api_key"):
            providers.append('polygon')
    
    return {"providers": providers}

# This should be the primary endpoint for fetching all backtests for the logged-in user
@router.get("/", response_model=List[BacktestSummary])
async def get_user_backtests_root(
    db: Database = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_from_token)
):
    """
    Retrieves a summary list of all backtests for the current user.

    This is the root endpoint for the backtest API and provides a high-level
    overview of each backtest, including key performance metrics.

    Args:
        db: The database connection instance.
        current_user: The authenticated user.

    Returns:
        A list of backtest summaries.
    """
    backtests_cursor = db.backtests.find({"user_id": current_user.id})
    backtests = await run_db_operation(list, backtests_cursor)
    
    summaries = []
    for backtest in backtests:
        stats = backtest.get("stats", {})
        summary = BacktestSummary(
            id=str(backtest["_id"]),
            strategy_id=str(backtest.get("strategy_id", "")),
            strategy_name=backtest.get("strategy_name", ""),
            total_return=stats.get("total_return_pct", stats.get("total_return", 0)),
            sharpe_ratio=stats.get("sharpe_ratio", 0),
            max_drawdown=stats.get("max_drawdown", 0),
            total_trades=stats.get("total_trades", 0),
            start_date=backtest.get("start_date", ""),
            end_date=backtest.get("end_date", ""),
            created_at=backtest.get("created_at", datetime.utcnow())
        )
        summaries.append(summary)
    return summaries

class EquityPoint(BaseModel):
    timestamp: str
    value: float
    cash: float
    positions_value: float


# Update the get_user_backtests_detailed endpoint to handle the actual MongoDB structure

@router.get("/user", response_model=None)
async def get_user_backtests(
    db: Database = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_from_token)
):
    """
    Retrieves detailed results for all backtests belonging to the current user.
    Returns the raw backtest documents from the database.
    """
    try:
        # Get all backtests for the user from the backtests collection
        backtests_cursor = db.backtests.find({"user_id": current_user.id})
        backtests = await run_db_operation(list, backtests_cursor)
        
        if not backtests:
            logger.info(f"No backtests found for user_id: {current_user.id}")
            return []

        # Convert ObjectId to string for JSON serialization
        for backtest in backtests:
            if "_id" in backtest:
                backtest["backtest_id"] = str(backtest.pop("_id"))
            if "user_id" in backtest:
                backtest["user_id"] = str(backtest["user_id"])
            if "strategy_id" in backtest:
                backtest["strategy_id"] = str(backtest["strategy_id"])
                
            # Ensure datetimes are serialized
            for date_field in ['created_at', 'completed_at', 'start_date', 'end_date']:
                if date_field in backtest and isinstance(backtest[date_field], (datetime, date)):
                    backtest[date_field] = backtest[date_field].isoformat()

        return backtests
        
    except Exception as e:
        logger.error(f"Error fetching user backtests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch backtest data: {str(e)}")