from pymongo.database import Database
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from ..utils.portfolio_manager import Position, Trade, Portfolio

logger = logging.getLogger(__name__)

class StrategyPersistence:
    """
    Handles persistence of portfolio positions and trades to MongoDB.
    Each user + strategy combination gets its own collections:
    - {user_id}_{strategy_id}_positions
    - {user_id}_{strategy_id}_trades
    """
    
    def __init__(self, db: Database, user_id: str, strategy_id: str):
        """
        Initialize persistence manager for a specific user and strategy.
        
        Args:
            db: MongoDB database instance
            user_id: User identifier
            strategy_id: Strategy identifier
        """
        self.db = db
        self.user_id = user_id
        self.strategy_id = strategy_id
        
        # Create collection names based on user and strategy
        self.positions_collection_name = f"user_{user_id}_strategy_{strategy_id}_positions"
        self.trades_collection_name = f"user_{user_id}_strategy_{strategy_id}_trades"
        self.portfolio_state_collection_name = f"user_{user_id}_strategy_{strategy_id}_portfolio"
        
        # Get collection references
        self.positions_collection = self.db[self.positions_collection_name]
        self.trades_collection = self.db[self.trades_collection_name]
        self.portfolio_state_collection = self.db[self.portfolio_state_collection_name]
    
    def initialize_collections(self):
        """Create indexes for better query performance."""
        try:
            # Index on positions collection
            self.positions_collection.create_index([("symbol", 1), ("entry_time", -1)])
            self.positions_collection.create_index([("position_id", 1)], unique=True)
            
            # Index on trades collection
            self.trades_collection.create_index([("symbol", 1), ("exit_time", -1)])
            self.trades_collection.create_index([("position_id", 1)])
            self.trades_collection.create_index([("exit_time", -1)])
            
            # Index on portfolio state
            self.portfolio_state_collection.create_index([("timestamp", -1)])
            
            logger.info(f"Initialized collections for user {self.user_id}, strategy {self.strategy_id}")
        except Exception as e:
            logger.error(f"Error initializing collections: {e}")
    
    # ===== Position Management =====
    
    def save_position(self, position: Position) -> bool:
        """
        Save or update a position in MongoDB.
        
        Args:
            position: Position object to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            position_dict = {
                "position_id": position.position_id,
                "symbol": position.symbol,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "entry_time": position.entry_time,
                "updated_at": datetime.now(),
            }
            
            # Upsert based on position_id
            self.positions_collection.update_one(
                {"position_id": position.position_id},
                {"$set": position_dict},
                upsert=True
            )
            logger.debug(f"Saved position {position.position_id} for {position.symbol}")
            return True
        except Exception as e:
            logger.error(f"Error saving position: {e}")
            return False
    
    def save_positions_bulk(self, positions: List[Position]) -> bool:
        """Save multiple positions in a single operation."""
        try:
            if not positions:
                return True
                
            operations = []
            for position in positions:
                position_dict = {
                    "position_id": position.position_id,
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "entry_price": position.entry_price,
                    "entry_time": position.entry_time,
                    "updated_at": datetime.now(),
                }
                operations.append({
                    "update_one": {
                        "filter": {"position_id": position.position_id},
                        "update": {"$set": position_dict},
                        "upsert": True
                    }
                })
            
            self.positions_collection.bulk_write(operations)
            logger.info(f"Saved {len(positions)} positions")
            return True
        except Exception as e:
            logger.error(f"Error saving positions bulk: {e}")
            return False
    
    def delete_position(self, position_id: str) -> bool:
        """Delete a position from MongoDB (when fully closed)."""
        try:
            result = self.positions_collection.delete_one({"position_id": position_id})
            logger.debug(f"Deleted position {position_id}, count: {result.deleted_count}")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting position: {e}")
            return False
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Retrieve all open positions for this user/strategy."""
        try:
            cursor = self.positions_collection.find({})
            positions = list(cursor)
            return positions
        except Exception as e:
            logger.error(f"Error retrieving positions: {e}")
            return []
    
    # ===== Trade Management =====
    
    def save_trade(self, trade: Trade) -> bool:
        """
        Save a completed trade to MongoDB.
        
        Args:
            trade: Trade object to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            trade_dict = trade.to_dict()
            trade_dict["created_at"] = datetime.now()
            
            result = self.trades_collection.insert_one(trade_dict)
            logger.info(f"Saved trade for {trade.symbol}: P&L={trade.pnl:.2f} {trade.pnl_emoji}")
            return True
        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return False
    
    def save_trades_bulk(self, trades: List[Trade]) -> bool:
        """Save multiple trades in a single operation."""
        try:
            if not trades:
                return True
                
            trade_dicts = []
            for trade in trades:
                trade_dict = trade.to_dict()
                trade_dict["created_at"] = datetime.now()
                trade_dicts.append(trade_dict)
            
            result = self.trades_collection.insert_many(trade_dicts)
            logger.info(f"Saved {len(result.inserted_ids)} trades")
            return True
        except Exception as e:
            logger.error(f"Error saving trades bulk: {e}")
            return False
    
    def get_all_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve all trades for this user/strategy, ordered by exit time."""
        try:
            cursor = self.trades_collection.find({}).sort("exit_time", -1)
            if limit:
                cursor = cursor.limit(limit)
            trades = list(cursor)
            return trades
        except Exception as e:
            logger.error(f"Error retrieving trades: {e}")
            return []
    
    def get_trades_by_symbol(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve trades for a specific symbol."""
        try:
            cursor = self.trades_collection.find({"symbol": symbol}).sort("exit_time", -1)
            if limit:
                cursor = cursor.limit(limit)
            trades = list(cursor)
            return trades
        except Exception as e:
            logger.error(f"Error retrieving trades for {symbol}: {e}")
            return []
    
    def get_trade_statistics(self) -> Dict[str, Any]:
        """Calculate aggregate statistics from saved trades."""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_trades": {"$sum": 1},
                        "total_pnl": {"$sum": "$pnl"},
                        "avg_pnl": {"$avg": "$pnl"},
                        "winning_trades": {
                            "$sum": {"$cond": [{"$gt": ["$pnl", 0]}, 1, 0]}
                        },
                        "losing_trades": {
                            "$sum": {"$cond": [{"$lt": ["$pnl", 0]}, 1, 0]}
                        },
                        "max_win": {"$max": "$pnl"},
                        "max_loss": {"$min": "$pnl"},
                    }
                }
            ]
            
            result = list(self.trades_collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                stats["win_rate"] = (stats["winning_trades"] / stats["total_trades"] * 100) if stats["total_trades"] > 0 else 0
                return stats
            return {
                "total_trades": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "max_win": 0,
                "max_loss": 0,
            }
        except Exception as e:
            logger.error(f"Error calculating trade statistics: {e}")
            return {}
    
    # ===== Portfolio State Management =====
    
    def save_portfolio_snapshot(self, portfolio: Portfolio, current_prices: Dict[str, float] = None) -> bool:
        """
        Save a snapshot of the entire portfolio state.
        Useful for tracking equity curve and portfolio history.
        
        Args:
            portfolio: Portfolio object
            current_prices: Dict of symbol -> current price
            
        Returns:
            bool: True if successful
        """
        try:
            # Build positions data
            positions_data = {}
            for symbol, lots in portfolio.positions.items():
                positions_data[symbol] = [
                    {
                        "position_id": lot.position_id,
                        "quantity": lot.quantity,
                        "entry_price": lot.entry_price,
                        "entry_time": lot.entry_time,
                    }
                    for lot in lots
                ]
            
            snapshot = {
                "timestamp": datetime.now(),
                "cash": portfolio.cash,
                "total_value": portfolio.get_total_value(current_prices),
                "positions": positions_data,
                "total_trades": len(portfolio.trades),
                "realized_pnl": sum(t.pnl for t in portfolio.trades),
            }
            
            self.portfolio_state_collection.insert_one(snapshot)
            logger.debug(f"Saved portfolio snapshot: total_value={snapshot['total_value']:.2f}")
            return True
        except Exception as e:
            logger.error(f"Error saving portfolio snapshot: {e}")
            return False
    
    def get_portfolio_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve portfolio snapshots for historical analysis."""
        try:
            cursor = self.portfolio_state_collection.find({}).sort("timestamp", -1).limit(limit)
            history = list(cursor)
            return history
        except Exception as e:
            logger.error(f"Error retrieving portfolio history: {e}")
            return []
    
    # ===== Sync Portfolio to DB =====
    
    def sync_portfolio_to_db(self, portfolio: Portfolio, current_prices: Dict[str, float] = None) -> bool:
        """
        Full sync of portfolio to database.
        Saves all open positions and creates a snapshot.
        
        Args:
            portfolio: Portfolio object to sync
            current_prices: Optional current prices dict
            
        Returns:
            bool: True if successful
        """
        try:
            # Save all open positions
            all_positions = []
            for symbol, lots in portfolio.positions.items():
                all_positions.extend(lots)
            
            if all_positions:
                self.save_positions_bulk(all_positions)
            
            # Save portfolio snapshot
            self.save_portfolio_snapshot(portfolio, current_prices)
            
            logger.info(f"Synced portfolio to DB: {len(all_positions)} positions, {len(portfolio.trades)} total trades")
            return True
        except Exception as e:
            logger.error(f"Error syncing portfolio to DB: {e}")
            return False
    
    # ===== Cleanup =====
    
    def clear_all_data(self) -> bool:
        """Clear all data for this user/strategy (use with caution!)."""
        try:
            self.positions_collection.delete_many({})
            self.trades_collection.delete_many({})
            self.portfolio_state_collection.delete_many({})
            logger.warning(f"Cleared all data for user {self.user_id}, strategy {self.strategy_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            return False