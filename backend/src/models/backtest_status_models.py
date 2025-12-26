from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

class BacktestStatus(str, Enum):
    """Backtest execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class BacktestExecution(BaseModel):
    """Model for tracking backtest execution"""
    id: str = Field(..., description="Unique execution ID")
    user_id: str = Field(..., description="User ID")
    strategy_id: str = Field(..., description="Strategy ID")
    strategy_name: str = Field(..., description="Strategy name")
    status: BacktestStatus = Field(default=BacktestStatus.PENDING, description="Execution status")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Start time")
    end_time: Optional[datetime] = Field(None, description="End time")
    progress: float = Field(default=0.0, description="Progress percentage (0-100)")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    params: Dict[str, Any] = Field(..., description="Backtest parameters")
    result: Optional[Dict[str, Any]] = Field(None, description="Backtest result")
    
    model_config = ConfigDict(validate_by_name=True)
