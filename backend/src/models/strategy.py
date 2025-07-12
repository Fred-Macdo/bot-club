from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId
from ..utils.mongo_helpers import PyObjectId

class Indicator(BaseModel):
    """Technical indicator configuration"""
    name: str = Field(..., description="Indicator name (SMA, EMA, RSI, etc.)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Indicator parameters")
    
    @field_validator('name')
    @classmethod
    def validate_name_lowercase(cls, v):
        """Convert indicator name to lowercase"""
        return v.lower() if isinstance(v, str) else v

class Condition(BaseModel):
    """Trading condition for entry/exit"""
    indicator: str = Field(..., description="Indicator or price field to compare")
    comparison: str = Field(..., description="Comparison operator (above, below, crosses_above, etc.)")
    value: Any = Field(..., description="Value to compare against (number or indicator name)")
    
    @field_validator('indicator', 'comparison')
    @classmethod
    def validate_strings_lowercase(cls, v):
        """Convert indicator and comparison to lowercase"""
        return v.lower() if isinstance(v, str) else v

class RiskManagement(BaseModel):
    """Risk management parameters"""
    position_sizing_method: str = Field(default="risk_based", description="Position sizing method")
    risk_per_trade: float = Field(default=0.02, description="Risk per trade as decimal (2% = 0.02)")
    stop_loss: float = Field(default=0.05, description="Stop loss as decimal (5% = 0.05)")
    take_profit: float = Field(default=0.10, description="Take profit as decimal (10% = 0.10)")
    max_position_size: float = Field(default=10000.0, description="Maximum position size in dollars")
    atr_multiplier: float = Field(default=2.0, description="ATR multiplier for position sizing")
    
    @field_validator('position_sizing_method')
    @classmethod
    def validate_position_sizing_lowercase(cls, v):
        """Convert position sizing method to lowercase"""
        return v.lower() if isinstance(v, str) else v

class StrategyConfig(BaseModel):
    """Strategy configuration"""
    symbols: List[str] = Field(..., description="Trading symbols")
    timeframe: str = Field(..., description="Chart timeframe (1d, 1h, 15m, etc.)")
    start_date: str = Field(..., description="Strategy start date")
    end_date: str = Field(..., description="Strategy end date")
    entry_conditions: List[Condition] = Field(default_factory=list, description="Entry conditions")
    exit_conditions: List[Condition] = Field(default_factory=list, description="Exit conditions")
    risk_management: RiskManagement = Field(default_factory=RiskManagement, description="Risk management settings")
    indicators: List[Indicator] = Field(default_factory=list, description="Required technical indicators")
    
    @field_validator('symbols')
    @classmethod
    def validate_symbols_lowercase(cls, v):
        """Convert all symbols to lowercase"""
        if isinstance(v, list):
            return [symbol.lower() if isinstance(symbol, str) else symbol for symbol in v]
        return v
    
    @field_validator('timeframe')
    @classmethod
    def validate_timeframe_lowercase(cls, v):
        """Convert timeframe to lowercase"""
        return v.lower() if isinstance(v, str) else v

class BacktestResult(BaseModel):
    """Backtest results"""
    strategy_id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    total_return: float = Field(..., description="Total return percentage")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    win_rate: float = Field(..., description="Win rate percentage")
    total_trades: int = Field(..., description="Total number of trades")
    profit_factor: float = Field(..., description="Profit factor")
    initial_capital: float = Field(..., description="Initial capital amount")
    final_capital: float = Field(..., description="Final capital amount")
    start_date: str = Field(..., description="Backtest start date")
    end_date: str = Field(..., description="Backtest end date")
    timeframe: str = Field(..., description="Backtest timeframe")
    trades: List[Dict[str, Any]] = Field(default_factory=list, description="Individual trade details")
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list, description="Equity curve data")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Strategy(BaseModel):
    """Main strategy model"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId = Field(..., description="User who owns this strategy")
    name: str = Field(..., min_length=1, max_length=100, description="Strategy name")
    description: Optional[str] = Field(None, max_length=500, description="Strategy description")
    config: StrategyConfig = Field(..., description="Strategy configuration")
    is_active: bool = Field(default=False, description="Whether strategy is actively trading")
    is_paper: bool = Field(default=True, description="Whether this is paper trading")
    performance_stats: Optional[Dict[str, Any]] = Field(None, description="Live performance statistics")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('name', 'description')
    @classmethod
    def validate_strings_lowercase(cls, v):
        """Convert name and description to lowercase"""
        return v.lower() if isinstance(v, str) else v

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class StrategyCreate(BaseModel):
    """Model for creating a new strategy"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    config: StrategyConfig

class StrategyUpdate(BaseModel):
    """Model for updating a strategy"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    config: Optional[StrategyConfig] = None
    is_active: Optional[bool] = None
    is_paper: Optional[bool] = None

class StrategyResponse(BaseModel):
    """Response model for strategy data"""
    id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    config: StrategyConfig = Field(..., description="Strategy configuration")
    is_active: bool = Field(..., description="Whether strategy is active")
    is_paper: bool = Field(..., description="Whether this is paper trading")
    performance_stats: Optional[Dict[str, Any]] = Field(None, description="Performance statistics")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        validate_by_name = True

class BacktestParams(BaseModel):
    """Parameters for running a backtest"""
    start_date: str = Field(..., description="Backtest start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Backtest end date (YYYY-MM-DD)")
    initial_capital: float = Field(default=100000.0, description="Initial capital for backtest")
    timeframe: str = Field(default="1d", description="Data timeframe")

class BacktestResponse(BaseModel):
    """Response model for backtest results"""
    id: str = Field(..., description="Backtest result ID")
    strategy_id: str = Field(..., description="Strategy ID")
    total_return: float = Field(..., description="Total return percentage")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    win_rate: float = Field(..., description="Win rate percentage")
    total_trades: int = Field(..., description="Total number of trades")
    profit_factor: float = Field(..., description="Profit factor")
    initial_capital: float = Field(..., description="Initial capital")
    final_capital: float = Field(..., description="Final capital")
    start_date: str = Field(..., description="Backtest start date")
    end_date: str = Field(..., description="Backtest end date")
    timeframe: str = Field(..., description="Backtest timeframe")
    trades: List[Dict[str, Any]] = Field(..., description="Trade details")
    equity_curve: List[Dict[str, Any]] = Field(..., description="Equity curve")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        validate_by_name = True
