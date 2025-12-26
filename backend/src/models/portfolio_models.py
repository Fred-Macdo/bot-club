"""
Portfolio Data Models for Live Strategy Executor
Tracks positions, lots, trades, and performance for live trading strategies
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
import uuid
from bson import ObjectId


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


class LotSelectionMethod(str, Enum):
    """Methods for selecting which lots to sell"""
    FIFO = "fifo"  # First In First Out
    LIFO = "lifo"  # Last In First Out
    HIFO = "hifo"  # Highest In First Out (tax optimization)
    LOFO = "lofo"  # Lowest In First Out


class TradeType(str, Enum):
    """Trade types"""
    LONG = "long"
    SHORT = "short"
    

class TradeStatus(str, Enum):
    """Trade status"""
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class OrderStatus(str, Enum):
    """Order execution status"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


# ==================== LOT TRACKING ====================

class PositionLot(BaseModel):
    """
    Individual lot (purchase) within a position
    Used for DCA tracking and tax lot identification
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True
    )
    
    lot_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique lot identifier"
    )
    symbol: str = Field(..., description="Trading symbol")
    quantity: Decimal = Field(..., description="Number of shares in this lot")
    entry_price: Decimal = Field(..., description="Purchase price per share")
    entry_time: datetime = Field(
        default_factory=datetime.utcnow,
        description="Time of purchase"
    )
    cost_basis: Decimal = Field(
        default=Decimal('0'),
        description="Total cost (quantity * entry_price)"
    )
    
    # Tracking information
    strategy_id: str = Field(..., description="Strategy that created this lot")
    user_id: str = Field(..., description="User who owns this lot")
    
    # API integration
    alpaca_order_id: Optional[str] = Field(
        None,
        description="Alpaca order ID for tracking"
    )
    
    # Metadata
    notes: str = Field(default="", description="Notes (e.g., 'DCA entry 3')")
    entry_reason: Optional[str] = Field(None, description="Why this entry was made")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    
    @field_validator('quantity', 'entry_price', 'cost_basis', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v
    
    def model_post_init(self, __context):
        """Calculate cost basis if not provided"""
        if self.cost_basis == Decimal('0') and self.quantity and self.entry_price:
            self.cost_basis = self.quantity * self.entry_price
    
    def get_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L"""
        return (self.quantity * current_price) - self.cost_basis
    
    def get_unrealized_pnl_pct(self, current_price: Decimal) -> float:
        """Calculate unrealized P&L percentage"""
        if self.cost_basis == 0:
            return 0.0
        return float(self.get_unrealized_pnl(current_price) / self.cost_basis * 100)
    
    def get_holding_period_days(self, current_time: datetime = None) -> int:
        """Calculate holding period in days"""
        current_time = current_time or datetime.utcnow()
        return (current_time - self.entry_time).days


# ==================== TRADE TRACKING ====================

class CompletedTrade(BaseModel):
    """
    Completed trade record with full entry/exit information
    Represents a closed position or lot
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True
    )
    
    trade_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique trade identifier"
    )
    lot_id: str = Field(..., description="Original lot ID")
    
    # Core trade info
    symbol: str = Field(..., description="Trading symbol")
    trade_type: TradeType = Field(default=TradeType.LONG, description="Trade type")
    quantity: Decimal = Field(..., description="Number of shares traded")
    
    # Entry details
    entry_price: Decimal = Field(..., description="Entry price per share")
    entry_time: datetime = Field(..., description="Entry timestamp")
    entry_reason: Optional[str] = Field(None, description="Entry condition/reason")
    
    # Exit details
    exit_price: Decimal = Field(..., description="Exit price per share")
    exit_time: datetime = Field(..., description="Exit timestamp")
    exit_reason: Optional[str] = Field(None, description="Exit condition/reason")
    
    # P&L
    realized_pnl: Decimal = Field(..., description="Realized profit/loss")
    realized_pnl_pct: Optional[float] = Field(None, description="P&L percentage")
    
    # Tracking
    strategy_id: str = Field(..., description="Strategy that executed this trade")
    user_id: str = Field(..., description="User who owns this trade")
    
    # API integration
    entry_order_id: Optional[str] = Field(None, description="Entry order ID")
    exit_order_id: Optional[str] = Field(None, description="Exit order ID")
    
    # Metadata
    lot_selection_method: Optional[str] = Field(
        None,
        description="Method used to select this lot"
    )
    holding_period_days: Optional[int] = Field(
        None,
        description="Days held"
    )
    commission: Decimal = Field(
        default=Decimal('0'),
        description="Commission paid"
    )
    
    @field_validator('quantity', 'entry_price', 'exit_price', 'realized_pnl', 'commission', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v
    
    def model_post_init(self, __context):
        """Calculate derived fields"""
        if self.realized_pnl_pct is None and self.entry_price > 0:
            self.realized_pnl_pct = float(
                ((self.exit_price - self.entry_price) / self.entry_price) * 100
            )
        
        if self.holding_period_days is None:
            self.holding_period_days = (self.exit_time - self.entry_time).days


# ==================== ORDER EXECUTION ====================

class OrderExecution(BaseModel):
    """
    Order execution tracking
    Links strategy orders to API execution
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True
    )
    
    execution_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique execution identifier"
    )
    
    # Order details
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="buy or sell")
    order_type: str = Field(..., description="market, limit, etc.")
    quantity: Decimal = Field(..., description="Requested quantity")
    
    # Prices
    limit_price: Optional[Decimal] = Field(None, description="Limit price if applicable")
    stop_price: Optional[Decimal] = Field(None, description="Stop price if applicable")
    filled_price: Optional[Decimal] = Field(None, description="Average fill price")
    
    # Status
    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        description="Current order status"
    )
    filled_quantity: Decimal = Field(
        default=Decimal('0'),
        description="Quantity filled so far"
    )
    
    # Timestamps
    submitted_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When order was submitted"
    )
    filled_at: Optional[datetime] = Field(None, description="When order was filled")
    
    # API tracking
    api_order_id: Optional[str] = Field(None, description="Alpaca/broker order ID")
    error_message: Optional[str] = Field(None, description="Error if failed")
    
    # Strategy tracking
    strategy_id: str = Field(..., description="Strategy that created this order")
    user_id: str = Field(..., description="User who owns this order")
    
    # Bracket order details
    stop_loss_price: Optional[Decimal] = Field(None, description="Stop loss price")
    take_profit_price: Optional[Decimal] = Field(None, description="Take profit price")
    stop_loss_order_id: Optional[str] = Field(None, description="Stop loss order ID")
    take_profit_order_id: Optional[str] = Field(None, description="Take profit order ID")
    
    @field_validator('quantity', 'limit_price', 'stop_price', 'filled_price', 
                     'filled_quantity', 'stop_loss_price', 'take_profit_price', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


# ==================== PORTFOLIO STATE ====================

class PortfolioSnapshot(BaseModel):
    """
    Point-in-time snapshot of portfolio state
    Used for equity curve and performance tracking
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True
    )
    
    snapshot_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique snapshot identifier"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Snapshot timestamp"
    )
    
    # Portfolio values
    total_value: Decimal = Field(..., description="Total portfolio value")
    cash: Decimal = Field(..., description="Cash balance")
    positions_value: Decimal = Field(..., description="Market value of positions")
    
    # P&L
    unrealized_pnl: Decimal = Field(
        default=Decimal('0'),
        description="Unrealized P&L from open positions"
    )
    realized_pnl: Decimal = Field(
        default=Decimal('0'),
        description="Cumulative realized P&L"
    )
    
    # Position details
    position_count: int = Field(default=0, description="Number of open positions")
    lot_count: int = Field(default=0, description="Total number of lots")
    
    # Strategy tracking
    strategy_id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    
    @field_validator('total_value', 'cash', 'positions_value', 'unrealized_pnl', 'realized_pnl', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class PerformanceMetrics(BaseModel):
    """
    Performance metrics for a strategy
    Calculated from trades and portfolio history
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str},
        arbitrary_types_allowed=True
    )
    
    # Trade statistics
    total_trades: int = Field(default=0, description="Total number of trades")
    winning_trades: int = Field(default=0, description="Number of winning trades")
    losing_trades: int = Field(default=0, description="Number of losing trades")
    win_rate: float = Field(default=0.0, description="Win rate percentage")
    
    # P&L statistics
    total_pnl: Decimal = Field(default=Decimal('0'), description="Total P&L")
    total_pnl_pct: float = Field(default=0.0, description="Total return percentage")
    avg_win: Decimal = Field(default=Decimal('0'), description="Average winning trade")
    avg_loss: Decimal = Field(default=Decimal('0'), description="Average losing trade")
    largest_win: Decimal = Field(default=Decimal('0'), description="Largest winning trade")
    largest_loss: Decimal = Field(default=Decimal('0'), description="Largest losing trade")
    
    # Risk metrics
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    max_drawdown: Optional[float] = Field(None, description="Maximum drawdown %")
    max_drawdown_duration_days: Optional[int] = Field(
        None,
        description="Longest drawdown period in days"
    )
    
    # Position metrics
    avg_holding_period_days: Optional[float] = Field(
        None,
        description="Average holding period in days"
    )
    max_concurrent_positions: int = Field(
        default=0,
        description="Maximum concurrent positions held"
    )
    
    # DCA metrics
    total_dca_entries: int = Field(
        default=0,
        description="Total number of DCA entries"
    )
    avg_lots_per_position: float = Field(
        default=0.0,
        description="Average lots per position"
    )
    
    # Tracking
    strategy_id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When metrics were calculated"
    )
    
    @field_validator('total_pnl', 'avg_win', 'avg_loss', 'largest_win', 'largest_loss', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class StrategyPortfolio(BaseModel):
    """
    Complete portfolio state for a strategy
    Main model that aggregates all portfolio information
    """
    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
        arbitrary_types_allowed=True
    )
    
    portfolio_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique portfolio identifier"
    )
    
    # Identification
    strategy_id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    strategy_name: str = Field(..., description="Strategy name")
    
    # Capital
    initial_capital: Decimal = Field(..., description="Initial capital")
    current_cash: Decimal = Field(..., description="Current cash balance")
    
    # Positions and Lots
    lots: Dict[str, List[PositionLot]] = Field(
        default_factory=dict,
        description="Active lots grouped by symbol"
    )
    
    # Trade history
    completed_trades: List[CompletedTrade] = Field(
        default_factory=list,
        description="History of completed trades"
    )
    
    # Order tracking
    pending_orders: List[OrderExecution] = Field(
        default_factory=list,
        description="Orders awaiting execution"
    )
    
    # Performance
    performance: PerformanceMetrics = Field(
        ...,
        description="Current performance metrics"
    )
    
    # History
    equity_curve: List[PortfolioSnapshot] = Field(
        default_factory=list,
        description="Historical portfolio snapshots"
    )
    
    # Settings
    lot_selection_method: LotSelectionMethod = Field(
        default=LotSelectionMethod.FIFO,
        description="Default lot selection method"
    )
    
    # Status
    is_active: bool = Field(default=True, description="Whether portfolio is active")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Portfolio creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update time"
    )
    
    @field_validator('initial_capital', 'current_cash', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v
    
    def get_total_value(self, current_prices: Dict[str, Decimal]) -> Decimal:
        """Calculate total portfolio value"""
        positions_value = Decimal('0')
        for symbol, lots in self.lots.items():
            if symbol in current_prices:
                for lot in lots:
                    positions_value += lot.quantity * current_prices[symbol]
        return self.current_cash + positions_value
    
    def get_lot_count_for_symbol(self, symbol: str) -> int:
        """Get number of lots for a symbol (for DCA tracking)"""
        return len(self.lots.get(symbol, []))
    
    def get_position_quantity(self, symbol: str) -> Decimal:
        """Get total quantity for a symbol across all lots"""
        return sum(lot.quantity for lot in self.lots.get(symbol, []))


# ==================== DATABASE DOCUMENT MODELS ====================

class StrategyPortfolioDocument(BaseModel):
    """
    MongoDB document model for StrategyPortfolio
    Flattened for efficient storage and querying
    """
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, Decimal: str, datetime: lambda v: v.isoformat()}
    )
    
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    portfolio_id: str = Field(..., description="Portfolio identifier")
    strategy_id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    strategy_name: str = Field(..., description="Strategy name")
    
    # Capital (stored as strings for Decimal precision)
    initial_capital: str = Field(..., description="Initial capital")
    current_cash: str = Field(..., description="Current cash")
    
    # Nested documents
    lots: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Serialized lots"
    )
    completed_trades: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized trades"
    )
    pending_orders: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized orders"
    )
    performance: Dict[str, Any] = Field(
        ...,
        description="Serialized performance metrics"
    )
    
    # Settings
    lot_selection_method: str = Field(default="fifo")
    is_active: bool = Field(default=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)
