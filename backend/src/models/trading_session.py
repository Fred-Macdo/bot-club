"""
Trading Session Models
Tracks live/paper trading sessions that persist independently of user login.
Each deployment creates a session document that stores:
- Session identity (strategy, user, task_id)
- Configuration (mode, data_provider, initial_capital)
- Runtime state (status, timestamps)
- Reference to the StrategyPortfolio for resumption
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import uuid


class TradingSessionStatus:
    PENDING = "pending"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    COMPLETED = "completed"
    SCHEDULED = "scheduled"  # Stock strategy waiting for next market open


class TradingSessionConfig(BaseModel):
    """Configuration snapshot for reproducibility"""

    mode: str = Field(..., description="'paper' or 'live'")
    data_provider: str = Field(default="alpaca", description="Data provider name")
    initial_capital: float = Field(
        default=100000.0, description="User-defined initial capital"
    )
    timeframe: str = Field(default="15M", description="Trading timeframe")
    symbols: list[str] = Field(default_factory=list, description="Symbols being traded")
    asset_type: str = Field(default="crypto", description="'crypto' or 'stock'")
    extended_hours: bool = Field(
        default=False, description="Include pre/post-market hours for stocks"
    )
    schedule_name: Optional[str] = Field(
        default=None, description="RedBeat schedule entry name for stock strategies"
    )


class TradingSession(BaseModel):
    """
    Persistent trading session document stored in MongoDB.
    Created on deploy, updated on each iteration, read on reconnect.
    """

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session identifier",
    )
    strategy_id: str = Field(..., description="Strategy being executed")
    strategy_name: str = Field(
        default="Unknown Strategy", description="Human-readable strategy name"
    )
    user_id: str = Field(..., description="Owner of this session")

    # Celery task tracking
    task_id: Optional[str] = Field(None, description="Celery task ID for this session")

    # Configuration
    config: TradingSessionConfig = Field(..., description="Session configuration")

    # Full strategy configuration (indicators, conditions, risk) for UI restoration
    strategy_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Full strategy config snapshot for session restore"
    )

    # Status
    status: str = Field(
        default=TradingSessionStatus.PENDING, description="Current session status"
    )
    error_message: Optional[str] = Field(
        None, description="Error details if status is 'error'"
    )

    # Portfolio reference — the portfolio_id in strategy_portfolios collection
    portfolio_id: Optional[str] = Field(
        None, description="Portfolio ID for resumption (references strategy_portfolios)"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    started_at: Optional[datetime] = Field(
        None, description="When trading actually began"
    )
    stopped_at: Optional[datetime] = Field(None, description="When trading stopped")
    last_iteration_at: Optional[datetime] = Field(
        None, description="Last successful iteration"
    )
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Iteration counter
    iteration_count: int = Field(
        default=0, description="Number of completed iterations"
    )
