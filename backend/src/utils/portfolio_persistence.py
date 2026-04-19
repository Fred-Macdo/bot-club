from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from bson import ObjectId
import logging
import json

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types"""
    def default(self, obj):
        if isinstance(Decimal, obj):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


class PortfolioPersistence:
    """
    Handles MongoDB persistence and Redis stream publishing for portfolio updates.
    """
    
    def __init__(self, db, stream_publisher, strategy_id: str, user_id: str, mode: str = 'paper'):
        """
        Args:
            db: MongoDB database instance
            stream_publisher: Function to publish to Redis stream (event_type, payload)
            strategy_id: The strategy ID
            user_id: The user ID
            mode: Trading mode ('paper' or 'live')
        """
        self.db = db
        self.stream_publisher = stream_publisher
        self.strategy_id = str(strategy_id)
        self.user_id = str(user_id)
        self.mode = mode
        
    def _serialize_for_mongo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Decimal and other types for MongoDB storage"""
        result = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
            elif isinstance(value, dict):
                result[key] = self._serialize_for_mongo(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_for_mongo(v) if isinstance(v, dict) 
                    else float(v) if isinstance(v, Decimal) 
                    else v 
                    for v in value
                ]
            else:
                result[key] = value
        return result
    
    def _serialize_for_redis(self, data: Dict[str, Any]) -> str:
        """Serialize data for Redis stream"""
        return json.dumps(data, cls=DecimalEncoder, default=str)

    # ==================== BUY OPERATIONS ====================
    
    def save_buy(self, lot: Any) -> Optional[str]:
        """
        Save a new position lot to MongoDB and publish to Redis.
        
        Args:
            lot: PositionLot object
            
        Returns:
            The inserted document ID or None
        """
        try:
            lot_data = lot.model_dump() if hasattr(lot, 'model_dump') else lot.__dict__.copy()
            lot_data['strategy_id'] = self.strategy_id
            lot_data['user_id'] = self.user_id
            lot_data['mode'] = self.mode
            lot_data['created_at'] = datetime.now(tz=timezone.utc)
            lot_data['status'] = 'open'
            
            mongo_data = self._serialize_for_mongo(lot_data)
            
            # Save to MongoDB
            if self.db is not None:
                result = self.db.position_lots.insert_one(mongo_data)
                lot_data['_id'] = str(result.inserted_id)
                logger.info(f"Saved position lot to MongoDB: {result.inserted_id}")
            
            # Publish to Redis stream
            if self.stream_publisher:
                self.stream_publisher("position_opened", {
                    "event_type": "position_opened",
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "strategy_id": self.strategy_id,
                    "user_id": self.user_id,
                    "lot": {
                        "lot_id": lot_data.get('lot_id', str(lot_data.get('_id', ''))),
                        "symbol": lot_data.get('symbol'),
                        "quantity": float(lot_data.get('quantity', 0)),
                        "entry_price": float(lot_data.get('entry_price', 0)),
                        "entry_time": lot_data.get('entry_time').isoformat() if isinstance(lot_data.get('entry_time'), datetime) else str(lot_data.get('entry_time')),
                        "cost_basis": float(lot_data.get('cost_basis', 0)),
                        "entry_reason": lot_data.get('entry_reason', '')
                    }
                })
                
            return lot_data.get('_id')
            
        except Exception as e:
            logger.error(f"Error saving buy to MongoDB/Redis: {e}")
            return None

    # ==================== SELL OPERATIONS ====================
    
    def save_completed_trade(self, trade: Any) -> Optional[str]:
        """
        Save a completed trade to MongoDB and publish to Redis.
        
        Args:
            trade: CompletedTrade object
            
        Returns:
            The inserted document ID or None
        """
        try:
            trade_data = trade.model_dump() if hasattr(trade, 'model_dump') else trade.__dict__.copy()
            trade_data['strategy_id'] = self.strategy_id
            trade_data['user_id'] = self.user_id
            trade_data['mode'] = self.mode
            trade_data['created_at'] = datetime.now(tz=timezone.utc)
            
            mongo_data = self._serialize_for_mongo(trade_data)
            
            # Save to MongoDB
            if self.db is not None:
                result = self.db.completed_trades.insert_one(mongo_data)
                trade_data['_id'] = str(result.inserted_id)
                logger.info(f"Saved completed trade to MongoDB: {result.inserted_id}")
                
                # Also mark the original lot as closed
                if trade_data.get('lot_id'):
                    self.db.position_lots.update_one(
                        {'lot_id': trade_data['lot_id']},
                        {'$set': {
                            'status': 'closed',
                            'closed_at': datetime.now(tz=timezone.utc),
                            'exit_price': float(trade_data.get('exit_price', 0)),
                            'exit_time': trade_data.get('exit_time'),
                            'realized_pnl': float(trade_data.get('realized_pnl', 0))
                        }}
                    )
            
            # Publish to Redis stream
            if self.stream_publisher:
                self.stream_publisher("trade_completed", {
                    "event_type": "trade_completed",
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "strategy_id": self.strategy_id,
                    "user_id": self.user_id,
                    "trade": {
                        "trade_id": trade_data.get('trade_id', str(trade_data.get('_id', ''))),
                        "lot_id": trade_data.get('lot_id', ''),
                        "symbol": trade_data.get('symbol'),
                        "quantity": float(trade_data.get('quantity', 0)),
                        "entry_price": float(trade_data.get('entry_price', 0)),
                        "exit_price": float(trade_data.get('exit_price', 0)),
                        "entry_time": trade_data.get('entry_time').isoformat() if isinstance(trade_data.get('entry_time'), datetime) else str(trade_data.get('entry_time')),
                        "exit_time": trade_data.get('exit_time').isoformat() if isinstance(trade_data.get('exit_time'), datetime) else str(trade_data.get('exit_time')),
                        "realized_pnl": float(trade_data.get('realized_pnl', 0)),
                        "return_pct": float(trade_data.get('return_pct', 0)),
                        "exit_reason": trade_data.get('exit_reason', '')
                    }
                })
                
            return trade_data.get('_id')
            
        except Exception as e:
            logger.error(f"Error saving completed trade to MongoDB/Redis: {e}")
            return None

    # ==================== PORTFOLIO SNAPSHOT ====================
    
    def save_portfolio_snapshot(self, portfolio: Any, latest_prices: Dict[str, float]) -> Optional[str]:
        """
        Save portfolio snapshot to MongoDB and publish full portfolio update to Redis.
        
        Args:
            portfolio: StrategyPortfolio object
            latest_prices: Dict of symbol -> current price
            
        Returns:
            The inserted document ID or None
        """
        try:
            portfolio_data = portfolio.model_dump() if hasattr(portfolio, 'model_dump') else portfolio.__dict__.copy()
            
            # Calculate current values
            positions_value = Decimal(0)
            unrealized_pnl = Decimal(0)
            
            lots_list = []
            for symbol, lots in portfolio_data.get('lots', {}).items():
                price = latest_prices.get(symbol)
                if price is not None:
                    for lot in lots:
                        qty = Decimal(str(lot.get('quantity', 0)))
                        entry_price = Decimal(str(lot.get('entry_price', 0)))
                        current_price = Decimal(str(price))
                        
                        positions_value += qty * current_price
                        unrealized_pnl += (current_price - entry_price) * qty
                        
                        lots_list.append({
                            'lot_id': lot.get('lot_id', ''),
                            'symbol': symbol,
                            'quantity': float(qty),
                            'entry_price': float(entry_price),
                            'entry_time': lot.get('entry_time').isoformat() if isinstance(lot.get('entry_time'), datetime) else str(lot.get('entry_time')),
                            'cost_basis': float(lot.get('cost_basis', 0)),
                            'current_price': float(current_price),
                            'unrealized_pnl': float((current_price - entry_price) * qty)
                        })
            
            current_cash = Decimal(str(portfolio_data.get('current_cash', 0)))
            total_value = current_cash + positions_value
            initial_capital = Decimal(str(portfolio_data.get('initial_capital', 0)))
            
            # Build snapshot
            snapshot = {
                'strategy_id': self.strategy_id,
                'user_id': self.user_id,
                'timestamp': datetime.now(tz=timezone.utc),
                'cash': float(current_cash),
                'positions_value': float(positions_value),
                'total_value': float(total_value),
                'unrealized_pnl': float(unrealized_pnl),
                'realized_pnl': float(portfolio_data.get('performance', {}).get('total_pnl', 0)),
                'total_return_pct': float((total_value - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0,
            }
            
            # Save to MongoDB
            if self.db is not None:
                result = self.db.portfolio_snapshots.insert_one(snapshot.copy())
                snapshot['_id'] = str(result.inserted_id)
                logger.info(f"Saved portfolio snapshot to MongoDB: {result.inserted_id}")
            
            # Publish full portfolio update to Redis
            if self.stream_publisher:
                performance = portfolio_data.get('performance', {})
                completed_trades = portfolio_data.get('completed_trades', [])
                
                # Serialize completed trades
                completed_trades_list = []
                for trade in completed_trades:
                    if hasattr(trade, 'model_dump'):
                        trade = trade.model_dump()
                    completed_trades_list.append({
                        'trade_id': trade.get('trade_id', ''),
                        'symbol': trade.get('symbol'),
                        'quantity': float(trade.get('quantity', 0)),
                        'entry_price': float(trade.get('entry_price', 0)),
                        'exit_price': float(trade.get('exit_price', 0)),
                        'realized_pnl': float(trade.get('realized_pnl', 0)),
                        'status': 'closed'
                    })
                
                self.stream_publisher("portfolio_update", {
                    "event_type": "portfolio_update",
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "strategy_id": self.strategy_id,
                    "user_id": self.user_id,
                    "strategy_name": portfolio_data.get('strategy_name', ''),
                    "initial_capital": float(initial_capital),
                    "current_cash": float(current_cash),
                    "positions_value": float(positions_value),
                    "total_value": float(total_value),
                    "lots": lots_list,
                    "completed_trades": completed_trades_list,
                    "pending_orders": [],
                    "performance": {
                        "total_pnl": float(performance.get('total_pnl', 0)),
                        "unrealized_pnl": float(unrealized_pnl),
                        "total_trades": int(performance.get('total_trades', 0)),
                        "winning_trades": int(performance.get('winning_trades', 0)),
                        "losing_trades": int(performance.get('losing_trades', 0)),
                        "win_rate": float(performance.get('win_rate', 0)),
                        "avg_win": float(performance.get('avg_win', 0)),
                        "avg_loss": float(performance.get('avg_loss', 0)),
                        "total_return_pct": snapshot['total_return_pct']
                    }
                })
                
            return snapshot.get('_id')
            
        except Exception as e:
            logger.error(f"Error saving portfolio snapshot to MongoDB/Redis: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ==================== EQUITY CURVE ====================
    
    def save_equity_point(self, total_value: Decimal, cash: Decimal, positions_value: Decimal) -> Optional[str]:
        """
        Save an equity curve data point to MongoDB and publish to Redis.
        """
        try:
            equity_point = {
                'strategy_id': self.strategy_id,
                'user_id': self.user_id,
                'timestamp': datetime.now(tz=timezone.utc),
                'total_value': float(total_value),
                'cash': float(cash),
                'positions_value': float(positions_value)
            }
            
            # Save to MongoDB
            if self.db is not None:
                result = self.db.equity_curve.insert_one(equity_point.copy())
                equity_point['_id'] = str(result.inserted_id)
            
            # Publish to Redis
            if self.stream_publisher:
                self.stream_publisher("equity_update", {
                    "event_type": "equity_update",
                    "timestamp": datetime.now(tz=timezone.utc).timestamp() * 1000,
                    "strategy_id": self.strategy_id,
                    "total_value": float(total_value),
                    "cash": float(cash),
                    "positions_value": float(positions_value)
                })
                
            return equity_point.get('_id')
            
        except Exception as e:
            logger.error(f"Error saving equity point: {e}")
            return None

    # ==================== SYNC FULL STATE ====================
    
    def sync_portfolio_to_db(self, portfolio: Any) -> bool:
        """
        Full sync of portfolio state to MongoDB (upsert pattern).
        Used for recovery and ensuring DB consistency.
        """
        try:
            portfolio_data = portfolio.model_dump() if hasattr(portfolio, 'model_dump') else portfolio.__dict__.copy()
            mongo_data = self._serialize_for_mongo(portfolio_data)
            mongo_data['updated_at'] = datetime.now(tz=timezone.utc)
            mongo_data['mode'] = self.mode
            
            if self.db is not None:
                self.db.strategy_portfolios.update_one(
                    {'strategy_id': self.strategy_id, 'user_id': self.user_id, 'mode': self.mode},
                    {'$set': mongo_data},
                    upsert=True
                )
                logger.info(f"Synced portfolio state to MongoDB for strategy {self.strategy_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error syncing portfolio to MongoDB: {e}")
            return False