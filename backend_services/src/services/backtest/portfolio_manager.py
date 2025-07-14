import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Represents an open trading position"""
    symbol: str
    shares: int
    entry_price: float
    entry_time: datetime
    entry_value: float
    
    def get_days_held(self, current_time: datetime) -> int:
        return (current_time - self.entry_time).days

@dataclass
class Trade:
    """Represents a completed trade"""
    symbol: str
    shares: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    trade_type: str = "long"
    pnl_emoji: str = "⚪"  # Add emoji field
    
    @property
    def pnl_pct(self) -> float:
        """Calculate P&L percentage"""
        return (self.exit_price - self.entry_price) / self.entry_price * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'quantity': self.shares,  # Use 'quantity' to match expected format
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'pnl': self.pnl,
            'trade_type': self.trade_type,
            'pnl_emoji': self.pnl_emoji,
            'return_pct': self.pnl_pct  # Add return percentage
        }

class Portfolio:
    """Portfolio tracking class"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}
        self.equity_history = []
    
    @property
    def total_value(self) -> float:
        total = self.cash
        for symbol, position in self.positions.items():
            position_value = position.shares * position.entry_price
            total += position_value
        return total
    
    def add_position(self, position: Position):
        self.positions[position.symbol] = position
    
    def remove_position(self, symbol: str):
        if symbol in self.positions:
            del self.positions[symbol]
    
    def open_position(self, symbol: str, row: Dict[str, Any], timestamp: datetime, risk_mgmt: Dict) -> Optional[Position]:
        """Open a new position"""
        entry_price = row.get('close', 0)
        if entry_price <= 0:
            return None
        
        risk_per_trade = risk_mgmt.get('risk_per_trade', 0.02)
        max_position_size = risk_mgmt.get('max_position_size', 10000)
        
        risk_amount = self.cash * risk_per_trade
        position_size = int(risk_amount / entry_price)
        
        if position_size <= 0:
            return None
        
        total_cost = position_size * entry_price
        
        if total_cost > max_position_size:
            position_size = int(max_position_size / entry_price)
            total_cost = position_size * entry_price
        
        if self.cash >= total_cost:
            self.cash -= total_cost
            
            position = Position(
                symbol=symbol,
                shares=position_size,
                entry_price=entry_price,
                entry_time=timestamp,
                entry_value=total_cost
            )
            
            self.add_position(position)
            logger.info(f"Opened position: {symbol} {position_size} shares at ${entry_price:.2f}")
            return position
        
        return None
    
    def close_position(self, position: Position, row: Dict[str, Any], timestamp: datetime) -> Trade:
        """Close an existing position"""
        exit_price = row.get('close', position.entry_price)
        exit_value = position.shares * exit_price
        
        self.cash += exit_value
        self.remove_position(position.symbol)
        
        pnl = exit_value - position.entry_value
        
        # Add emoji based on P&L
        pnl_emoji = "" if pnl > 0 else "" if pnl < 0 else "⚪"
        
        trade = Trade(
            symbol=position.symbol,
            shares=position.shares,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=timestamp,
            pnl=pnl,
            pnl_emoji=pnl_emoji
        )
        
        logger.info(f"Closed position: {pnl_emoji} {position.symbol} | PnL: ${pnl:.2f} ({trade.pnl_pct:.2f}%)")
        return trade
    
    def get_equity_curve(self) -> List[Dict[str, Any]]:
        return [
            {
                'timestamp': datetime.now().isoformat(),
                'value': self.total_value,
                'cash': self.cash,
                'positions_value': self.total_value - self.cash
            }
        ] 