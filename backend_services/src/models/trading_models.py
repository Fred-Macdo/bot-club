from pydantic import BaseModel, Field
from datetime import date, datetime
import uuid

from typing import List, Optional, Dict, Any
from bson import ObjectId
from ..services.utils.mongo_helpers import PyObjectId

class TradeData(BaseModel):
    """Individual trade data"""
    id: int = Field(..., description="Trade ID")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Trade side (buy/sell/long/short)")
    entry_date: str = Field(..., description="Entry date")
    entry_price: float = Field(..., description="Entry price")
    exit_date: str = Field(..., description="Exit date")
    exit_price: float = Field(..., description="Exit price")
    quantity: int = Field(..., description="Quantity traded")
    pnl: float = Field(..., description="Profit/Loss")
    return_pct: float = Field(..., description="Return percentage")
    data_context: Optional[List[Dict[str, Any]]] = Field(None, description="OHLCV data context around trade")