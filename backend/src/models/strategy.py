from datetime import datetime, timezone
from typing import List, Optional, Any, Dict, Literal, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict, BeforeValidator
from typing_extensions import Annotated
from bson import ObjectId
import uuid

from ..utils.asset_classifier import validate_no_mixed_assets
# Helper for ObjectId handling
PyObjectId = Annotated[str, BeforeValidator(str)]

class AccountTypeEnum(str, Enum):
    PAPER = "paper"
    LIVE = "live"

class StatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"

class Condition(BaseModel):
    """Trading condition for entry/exit"""
    indicator: str = Field(..., description="Indicator or price field to compare")
    comparison: str = Field(..., description="Comparison operator (above, below, crosses_above, etc.)")
    value: Union[str, float, int] = Field(..., description="Value to compare against (number or indicator name)")
    
    @field_validator('indicator', 'comparison')
    @classmethod
    def validate_strings_lowercase(cls, v):
        """Convert indicator and comparison to lowercase"""
        return v.lower() if isinstance(v, str) else v

class DollarCostAverage(BaseModel):
    """
    Configuration for Dollar Cost Averaging
    """
    enabled: bool = Field(default=False, description="Whether DCA is enabled")
    interval: str = Field(default="1d", description="DCA interval (1d, 1h, etc.)")
    max_attempts: int = Field(default=3, description="Maximum number of DCA attempts")
    amount_per_attempt: float = Field(default=100.0, description="Amount to invest per DCA attempt")
    
    @field_validator('interval')
    @classmethod
    def validate_interval_lowercase(cls, v):
        """Convert interval to lowercase"""
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
    start_date: Optional[str] = Field(None, description="Strategy start date")
    end_date: Optional[str] = Field(None, description="Strategy end date")
    entry_conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Entry conditions")
    exit_conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Exit conditions")
    risk_management: RiskManagement = Field(default_factory=RiskManagement, description="Risk management settings")
    indicators: List[Dict[str, Any]] = Field(default_factory=list, description="Required technical indicators")
    
    # FIX: Added this field so Pydantic doesn't strip it out
    dollar_cost_average: Optional[DollarCostAverage] = None

    @field_validator('symbols')
    @classmethod
    def validate_symbols_uppercase(cls, v):
        """Convert all symbols to uppercase and reject mixed crypto+stock."""
        if isinstance(v, list):
            upper = [symbol.upper() if isinstance(symbol, str) else symbol for symbol in v]
            validate_no_mixed_assets(upper)
            return upper
        return v
    
    @field_validator('timeframe')
    @classmethod
    def validate_timeframe_uppercase(cls, v):
        """Convert timeframe to uppercase"""
        return v.upper() if isinstance(v, str) else v

class StrategyCreate(BaseModel):
    """Model for creating a new strategy - no _id required"""
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_active: bool = False
    is_paper: bool = True
    
    class Config:
        extra = "ignore"  # Ignore extra fields like empty _id

class StrategyResponse(BaseModel):
    """Model for strategy response - includes _id"""
    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_active: bool = False
    is_paper: bool = True
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        populate_by_name = True

class Strategy(BaseModel):
    """Main strategy model"""
    id: PyObjectId = Field(default_factory=ObjectId, alias="_id")
    user_id: PyObjectId = Field(..., description="User who owns this strategy")
    name: str = Field(..., min_length=1, max_length=100, description="Strategy name")
    description: Optional[str] = Field(None, max_length=500, description="Strategy description")
    config: StrategyConfig = Field(..., description="Strategy configuration")
    is_active: bool = Field(default=False, description="Whether strategy is actively trading")
    is_paper: bool = Field(default=True, description="Whether this is paper trading")
    performance_stats: Optional[Dict[str, Any]] = Field(None, description="Live performance statistics")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    
    @field_validator('name', 'description')
    @classmethod
    def validate_strings_uppercase(cls, v):
        """Convert name and description to uppercase"""
        return v.upper() if isinstance(v, str) else v

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserStrategy(BaseModel):
    """
    Model for creating/updating a strategy
    """
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: str
    description: Optional[str] = None
    config: StrategyConfig # Uses the updated config model with DCA support
    is_active: bool = False
    is_paper: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: Optional[PyObjectId] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat()}
    )
