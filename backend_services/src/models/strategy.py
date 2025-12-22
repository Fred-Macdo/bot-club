from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId

def str_to_objectid(value):
    """Convert string to ObjectId if needed"""
    if isinstance(value, str):
        return ObjectId(value)
    return value

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")
        return field_schema


class Indicator(BaseModel):
    """Technical indicator configuration"""
    name: str = Field(..., description="Indicator name (SMA, EMA, RSI, etc.)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Indicator parameters")

class Condition(BaseModel):
    """Trading condition for entry/exit"""
    indicator: str = Field(..., description="Indicator or price field to compare")
    comparison: str = Field(..., description="Comparison operator (above, below, crosses_above, etc.)")
    value: Any = Field(..., description="Value to compare against (number or indicator name)")

class RiskManagement(BaseModel):
    """Risk management parameters"""
    position_sizing_method: str = Field(default="risk_based", description="Position sizing method")
    risk_per_trade: float = Field(default=0.02, description="Risk per trade as decimal (2% = 0.02)")
    stop_loss: float = Field(default=0.05, description="Stop loss as decimal (5% = 0.05)")
    take_profit: float = Field(default=0.10, description="Take profit as decimal (10% = 0.10)")
    max_position_size: float = Field(default=10000.0, description="Maximum position size in dollars")
    atr_multiplier: float = Field(default=2.0, description="ATR multiplier for position sizing")

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

    model_config = ConfigDict(validate_by_name=True, arbitrary_types_allowed=True)
