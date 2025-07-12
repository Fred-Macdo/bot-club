# backend/src/routes/backtest_routes.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid
import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import logging
from ..database.client import get_db
from ..models.backtest import BacktestParams, BacktestResponse, BacktestSummary
from ..models.strategy import Strategy
from ..models.user import UserInDB
from ..dependencies import get_current_user_from_token
from ..utils.redis_client import redis_client
from ..services.default_strategies import get_default_strategies_from_db

router = APIRouter(tags=["backtest"])
logger = logging.getLogger(__name__)

# Pydantic models for request/response
class BacktestRunRequest(BaseModel):
    strategy_id: str
    strategy_type: str  # 'default' or 'user'
    initial_capital: float
    timeframe: str
    start_date: str
    end_date: str
    data_provider: str

class BacktestRunResponse(BaseModel):
    backtest_id: str
    message: str

class BacktestStatus(BaseModel):
    status: str  # 'running', 'completed', 'failed'
    progress: int  # 0-100
    error: Optional[str] = None

class TradeDetail(BaseModel):
    id: int
    symbol: str
    side: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime]
    exit_price: Optional[float]
    quantity: float
    pnl: float
    return_pct: float

class EquityCurve(BaseModel):
    dates: List[datetime]
    total_equity: List[float]
    cash_balance: List[float]
    invested_capital: List[float]

class BacktestMetrics(BaseModel):
    initial_capital: float
    final_equity: float
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float

class BacktestResultResponse(BaseModel):
    backtest_id: str
    strategy_name: str
    equity_curve: EquityCurve
    trades: List[TradeDetail]
    metrics: BacktestMetrics

class TradeDetailsData(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    indicators: Dict[str, float]
    is_signal: bool

class TradeDetailsResponse(BaseModel):
    trade: TradeDetail
    entry_data: List[TradeDetailsData]
    exit_data: Optional[List[TradeDetailsData]] = None

class DeployRequest(BaseModel):
    strategy_id: str
    strategy_type: str
    mode: str  # 'paper' or 'live'
    initial_capital: float

class DeployResponse(BaseModel):
    success: bool
    deployment_id: str
    message: str

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
    db: AsyncIOMotorDatabase
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
            import requests
            
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
            
            response = requests.post(
                f"{backend_services_url}/backtest/run",
                json=backtest_payload
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
                
        except ImportError:
            # Fallback to mock implementation if requests is not available
            print("Warning: requests module not available, using mock implementation")
            
            # Simulate backtest execution
            await asyncio.sleep(1)  # Simulate processing time
            
            # Create mock results
            results = {
                "metrics": {
                    "final_equity": initial_capital * 1.1,  # 10% return
                    "total_return": 0.1,
                    "max_drawdown": -0.05,
                    "sharpe_ratio": 1.2,
                    "win_rate": 0.6,
                    "profit_factor": 1.5,
                    "total_trades": 10
                },
                "equity_curve": {
                    "dates": [start_date, end_date],
                    "total_equity": [initial_capital, initial_capital * 1.1],
                    "cash_balance": [initial_capital * 0.1, initial_capital * 0.2],
                    "invested_capital": [initial_capital * 0.9, initial_capital * 0.9]
                }
            }
            
            # Update status to completed
            await redis_client.hset(f"backtest:{backtest_id}", mapping={
                "status": "completed",
                "progress": 100
            })
        
        # Save results to database
        backtest_result_data = {
            "id": backtest_id,
            "user_id": user_id,
            "strategy_id": strategy_config['id'],
            "initial_capital": initial_capital,
            "final_equity": results['metrics']['final_equity'],
            "total_return": results['metrics']['total_return'],
            "max_drawdown": results['metrics']['max_drawdown'],
            "sharpe_ratio": results['metrics']['sharpe_ratio'],
            "win_rate": results['metrics']['win_rate'],
            "profit_factor": results['metrics']['profit_factor'],
            "total_trades": results['metrics']['total_trades'],
            "equity_curve": results['equity_curve'],
            "created_at": datetime.utcnow()
        }
        await db.backtest_results.insert_one(backtest_result_data)
        
        # Save trades
        if results['trades']:
            trades_to_insert = []
            for trade_data in results['trades']:
                trade = {
                    "backtest_id": backtest_id,
                    "symbol": trade_data['symbol'],
                    "side": trade_data['side'],
                    "entry_date": trade_data['entry_date'],
                    "entry_price": trade_data['entry_price'],
                    "exit_date": trade_data.get('exit_date'),
                    "exit_price": trade_data.get('exit_price'),
                    "quantity": trade_data['quantity'],
                    "pnl": trade_data['pnl'],
                    "return_pct": trade_data['return_pct']
                }
                trades_to_insert.append(trade)
            await db.trades.insert_many(trades_to_insert)
        
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
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Start a new backtest"""
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

        strategy = await db.strategy.find_one({
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
    """Get the status of a running backtest"""
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
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get the results of a completed backtest"""
    # Fetch backtest from database
    backtest = await db.backtest_results.find_one({
        "id": backtest_id,
        "user_id": current_user.id
    })
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest results not found")
    
    # Fetch trades
    trades_cursor = db.trades.find({"backtest_id": backtest_id})
    trades = await trades_cursor.to_list(length=None)
    
    # Get strategy name
    strategy = await db.strategies.find_one({"id": backtest["strategy_id"]})
    strategy_name = strategy["name"] if strategy else "Unknown Strategy"
    
    # Format response
    return BacktestResultResponse(
        backtest_id=backtest_id,
        strategy_name=strategy_name,
        equity_curve=EquityCurve(
            dates=backtest.equity_curve['dates'],
            total_equity=backtest.equity_curve['total_equity'],
            cash_balance=backtest.equity_curve['cash_balance'],
            invested_capital=backtest.equity_curve['invested_capital']
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
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get detailed OHLCV and indicator data for a specific trade"""
    # Verify backtest ownership
    backtest = await db.backtest_results.find_one({
        "id": backtest_id,
        "user_id": current_user.id
    })
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    # Get trade
    trade = await db.trades.find_one({
        "id": trade_id,
        "backtest_id": backtest_id
    })
    
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Get strategy configuration
    strategy = await db.strategies.find_one({"id": backtest["strategy_id"]})
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
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Deploy a strategy to live or paper trading"""
    # Load strategy configuration
    if request.strategy_type == 'default':
        default_strategies = await get_default_strategies_from_db(db)
        strategy_config = next((s for s in default_strategies if s["id"] == request.strategy_id), None)
        if not strategy_config:
            raise HTTPException(status_code=404, detail="Default strategy not found")
        strategy_name = strategy_config.get('name', 'Default Strategy')
    else:
        # Load user strategy
        strategy = await db.strategies.find_one({
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
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get available data providers for the current user"""
    providers = ['yahoo']  # Yahoo is always available
    
    # Check for configured API keys
    user_config = await db.user_configs.find_one({
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
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_from_token)
):
    """Get backtests for the current user (root endpoint)"""
    backtests_cursor = db.backtest_results.find({"user_id": current_user.id})
    backtests = await backtests_cursor.to_list(length=None)
    
    return [
        BacktestSummary(
            id=str(backtest["_id"]),
            strategy_id=str(backtest.get("strategy_id", "")),
            strategy_name=backtest.get("strategy_name", ""),
            total_return=backtest.get("total_return", 0),
            sharpe_ratio=backtest.get("sharpe_ratio", 0),
            max_drawdown=backtest.get("max_drawdown", 0),
            total_trades=backtest.get("total_trades", 0),
            start_date=backtest.get("start_date", ""),
            end_date=backtest.get("end_date", ""),
            created_at=backtest.get("created_at", datetime.utcnow())
        ) for backtest in backtests
    ]

@router.get("/user", response_model=List[BacktestSummary])
async def get_user_backtests(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_from_token)
):
    """Get backtests for the current user (user endpoint for frontend compatibility)"""
    backtests_cursor = db.backtest_results.find({"user_id": current_user.id})
    backtests = await backtests_cursor.to_list(length=None)
    
    return [
        BacktestSummary(
            id=str(backtest["_id"]),
            strategy_id=str(backtest.get("strategy_id", "")),
            strategy_name=backtest.get("strategy_name", ""),
            total_return=backtest.get("total_return", 0),
            sharpe_ratio=backtest.get("sharpe_ratio", 0),
            max_drawdown=backtest.get("max_drawdown", 0),
            total_trades=backtest.get("total_trades", 0),
            start_date=backtest.get("start_date", ""),
            end_date=backtest.get("end_date", ""),
            created_at=backtest.get("created_at", datetime.utcnow())
        ) for backtest in backtests
    ]