from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

class Position(BaseModel):
    """Represents a single FIFO lot for an open position."""
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="The unique identifier of the position")
    symbol: str = Field(..., description="The symbol of the position")
    quantity: float = Field(..., description="The quantity of the position")
    entry_price: float = Field(..., description="The entry price of the position")
    entry_time: datetime = Field(..., description="The entry time of the position")

class Trade(BaseModel):
    """Represents a realized trade (typically recorded on sells/trim)."""
    position_id: str = Field(..., description="The unique identifier of the position lot that was closed/trimmed")
    symbol: str = Field(..., description="The symbol of the trade")
    quantity: float = Field(..., description="The quantity closed")
    entry_price: float = Field(..., description="The original lot's entry price")
    exit_price: float = Field(..., description="The execution price of the trim/close")
    entry_time: datetime = Field(..., description="The lot's entry time")
    exit_time: datetime = Field(..., description="The time of the trim/close")
    pnl: float = Field(..., description="Realized P&L for this closed quantity")
    trade_type: str = Field(default="sell", description="Type of trade event (usually 'sell')")
    pnl_emoji: str = Field(..., description="Emoji representing result")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'pnl': self.pnl,
            'trade_type': self.trade_type,
            'pnl_emoji': self.pnl_emoji,
        }

class Portfolio(BaseModel):
    """Portfolio tracking with FIFO lots and realized trade log."""
    initial_capital: float = 0.0
    cash: float = 0.0
    positions: Dict[str, List[Position]] = Field(default_factory=dict, description="Symbol -> FIFO list of lots")
    equity_history: List[Dict[str, Any]] = Field(default_factory=list)
    trades: List[Trade] = Field(default_factory=list, description="Realized trades log")

    # Optional helper to set starting cash
    def set_initial_capital(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital

    def get_total_value(self, current_prices: Dict[str, float] = None) -> float:
        total = self.cash
        for symbol, lots in self.positions.items():
            for lot in lots:
                price = current_prices.get(symbol, lot.entry_price) if current_prices else lot.entry_price
                total += lot.quantity * price
        return total

    # --- Position management (FIFO lots) ---

    def add_buy(self, symbol: str, quantity: float, price: float, timestamp: datetime) -> Optional[Position]:
        """Adds a new FIFO lot (buy)."""
        if quantity <= 0 or price <= 0:
            return None
        cost = quantity * price
        if self.cash < cost:
            logger.warning(f"Insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
            return None

        self.cash -= cost
        lot = Position(
            symbol=symbol,
            quantity=float(quantity),
            entry_price=float(price),
            entry_time=timestamp,
        )
        self.positions.setdefault(symbol, []).append(lot)
        logger.info(f"BUY lot ({lot.position_id[:8]}): {symbol} {quantity} @ ${price:.2f} | cash={self.cash:.2f}")
        return lot

    def sell(self, symbol: str, quantity: float, price: float, timestamp: datetime) -> List[Trade]:
        """
        Trims/closes FIFO lots. Returns one or more Trade rows for realized P&L.
        If quantity exceeds open qty, closes all available.
        """
        realized_trades: List[Trade] = []
        if quantity <= 0 or price <= 0:
            return realized_trades

        lots = self.positions.get(symbol, [])
        qty_to_close = float(quantity)
        proceeds = 0.0

        i = 0
        while qty_to_close > 0 and i < len(lots):
            lot = lots[i]
            close_qty = min(lot.quantity, qty_to_close)
            pnl = (price - lot.entry_price) * close_qty
            proceeds += close_qty * price

            pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            trade = Trade(
                position_id=lot.position_id,
                symbol=symbol,
                quantity=close_qty,
                entry_price=round(lot.entry_price, 4),
                exit_price=round(price, 4),
                entry_time=lot.entry_time,
                exit_time=timestamp,
                pnl=round(pnl, 2),
                trade_type="sell",
                pnl_emoji=pnl_emoji,
            )
            self.trades.append(trade)
            realized_trades.append(trade)

            lot.quantity -= close_qty
            qty_to_close -= close_qty

            # Remove emptied lot
            if lot.quantity <= 0:
                lots.pop(i)
            else:
                i += 1

        # Cleanup empty symbol bucket
        if not lots and symbol in self.positions:
            del self.positions[symbol]

        # Apply cash proceeds
        if proceeds > 0:
            self.cash += proceeds
            logger.info(f"SELL {symbol} realized {len(realized_trades)} trades, proceeds=${proceeds:.2f}, cash={self.cash:.2f}")

        if qty_to_close > 0:
            logger.warning(f"Requested sell qty exceeded open qty for {symbol}; unfilled qty={qty_to_close}")

        return realized_trades

    # Convenience alias for partial closes
    def trim_position(self, symbol: str, quantity: float, price: float, timestamp: datetime) -> List[Trade]:
        return self.sell(symbol, quantity, price, timestamp)

    # Optional direct-lot helpers if you still want them
    def add_position(self, position: Position):
        self.positions.setdefault(position.symbol, []).append(position)

    def remove_position(self, symbol: str, position_id: str):
        if symbol in self.positions:
            self.positions[symbol] = [p for p in self.positions[symbol] if p.position_id != position_id]
            if not self.positions[symbol]:
                del self.positions[symbol]

    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Returns the history of equity values over time."""
        return self.equity_history