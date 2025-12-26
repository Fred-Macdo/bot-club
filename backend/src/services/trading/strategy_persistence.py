from pymongo.database import Database
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json
import redis
from ..utils.portfolio_manager import Position, Trade, Portfolio

logger = logging.getLogger(__name__)

class StrategyPersistence:
    """
    Handles persistence of portfolio positions and trades to MongoDB.
    Each user + strategy combination gets its own collections:
    - {user_id}_{strategy_id}_positions
    - {user_id}_{strategy_id}_trades
    - {user_id}_{strategy_id}_sessions (New)
    """
    
    def __init__(self, db: Database, user_id: str, strategy_id: str, redis_client: Optional[redis.Redis] = None):
        """
        Initialize persistence manager for a specific user and strategy.
        
        Args:
            db: MongoDB database instance
            user_id: User identifier
            strategy_id: Strategy identifier
            redis_client: Optional Redis client for session caching
        """
        self.db = db 
        self.user_id = user_id
        self.strategy_id = strategy_id
        self.redis_client = redis_client
        
        # Create collection names based on user and strategy
        self.session_collection_name = f"user_{user_id}_strategy_{strategy_id}"
        
        # Get collection references
        self.session_collection = self.db[self.session_collection_name]
    
    def initialize_collections(self):
        """Create indexes for better query performance."""
        try:
            # Index on session collection
            self.session_collection.create_index([("timestamp", -1)])
            
            logger.info(f"Initialized collections for user {self.user_id}, strategy {self.strategy_id}")
        except Exception as e:
            logger.error(f"Error initializing collections: {e}")
    
    # ===== Session Management (Redis + Mongo) =====

    def save_session(self, portfolio: Portfolio) -> bool:
        """
        Save the full portfolio state (Positions, Trades, Cash) to both MongoDB and Redis.
        Ensures state is preserved for browser refreshes or session restoration.
        """
        try:
            # 1. Serialize Portfolio to JSON-compatible dict (Pydantic v2)
            # mode='json' converts datetimes to ISO strings, suitable for Redis/JSON
            session_data = portfolio.model_dump(mode='json')
            
            # Add timestamp for tracking
            current_time = datetime.now()
            session_data['timestamp'] = current_time.isoformat()
            
            # 2. Save to Redis (Cache) - 24 hour expiry
            if self.redis_client:
                redis_key = f"session:{self.user_id}:{self.strategy_id}"
                self.redis_client.set(redis_key, json.dumps(session_data), ex=86400)
                logger.debug(f"Saved session to Redis: {redis_key}")
            
            # 3. Save to MongoDB (Persistence)
            # We add a native datetime object for Mongo querying/indexing
            mongo_doc = session_data.copy()
            mongo_doc['timestamp'] = current_time
            
            # Update specific fields without overwriting 'active' or 'task_id'
            self.session_collection.update_one(
                {},  # Match the single document in the collection (or we could add an _id if we wanted multiple)
                     # Since the collection is per user/strategy, it acts as a singleton for that session.
                     # However, to be safe, we might want to ensure we are updating the "latest" or "active" one?
                     # Given the structure "user_{user_id}_strategy_{strategy_id}_sessions", it implies a single active session context 
                     # or a history of sessions?
                     # The user said "add one session collection... and serialize... within it". 
                     # Usually "sessions" implies history. But "active" implies current state.
                     # Let's assume there's one "HEAD" document for the current state.
                     # But `save_session` was doing `insert_one` before! That means it WAS creating history.
                     # If we want to maintain an "active" flag on the *current* session, we should probably update the *latest* document
                     # or have a separate "state" document vs "history" documents.
                     #
                     # Compromise: We insert new documents for history (snapshots), but we ALSO update a "current_state" document?
                     # OR we just flag the *last inserted* document as active?
                     #
                     # "The document itself needs to be marked active".
                     # If we insert a new doc every time `save_session` is called (snapshotting), we have many docs.
                     # Mark the *latest* one as active?
                     # 
                     # Re-reading: "The document itself needs to be marked `active` when deployed. When `stop_strategy` is called it will need to be marked inactive."
                     # If `save_session` is called repeatedly (snapshots), do we mark ALL of them active?
                     #
                     # Maybe we should change `save_session` to UPDATE the current session document instead of inserting new ones constantly?
                     # `strategy_persistence.py` line 71: `self.session_collection.insert_one(mongo_doc)`
                     # This creates a new doc every time `sync_portfolio_to_db` is called (every trade/position update).
                     # This will flood the DB if we are not careful, but maybe that's the intent (audit trail).
                     #
                     # If we want the frontend to find "the active session", we need a way to distinguish the *current running* session from history.
                     #
                     # Proposal:
                     # 1. We have `insert_one` for history (snapshots).
                     # 2. We maintain a separate "active_session" collection or document? 
                     #    OR we update the *most recent* document?
                     #    OR we use a specific ID for the active session?
                     #
                     # User said: "The document itself needs to be marked active".
                     # If I start a strategy, I create a session doc.
                     # Updates should probably update THAT doc, not create new ones, OR create new ones that share a `session_id`.
                     #
                     # Let's look at `StockStrategy`. It calls `sync_portfolio_to_db` on every event.
                     # If `save_session` does `insert_one`, we get 1000s of docs.
                     # Ideally `save_session` should UPDATE the current state.
                     # And we use `save_portfolio_snapshot` (which calls `save_session` currently) for history?
                     #
                     # Let's change `save_session` to `update_one` (upsert) the "current state".
                     # And maybe add a `save_history` method if we want snapshots.
                     # Given the user wants to "save space in the db", `update_one` is better than `insert_one` loop.
                     
                {"$set": mongo_doc},
                upsert=True
            )
            
            logger.info(f"Saved session document for strategy {self.strategy_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False

    def set_session_active(self, active: bool, task_id: str = None):
        """
        Update the active status of the session.
        """
        try:
            update_data = {"active": active}
            if task_id:
                update_data["task_id"] = task_id
            
            self.session_collection.update_one(
                {}, 
                {"$set": update_data},
                upsert=True
            )
            logger.info(f"Updated session active status to {active}")
            return True
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
            return False


    def load_session(self) -> Optional[Portfolio]:
        """
        Retrieve the latest session state from Redis (preferred) or MongoDB.
        """
        try:
            data = None
            
            # 1. Try Redis first
            if self.redis_client:
                redis_key = f"session:{self.user_id}:{self.strategy_id}"
                cached_data = self.redis_client.get(redis_key)
                if cached_data:
                    data = json.loads(cached_data)
                    logger.info(f"Loaded session state from Redis: {redis_key}")

            # 2. Fallback to MongoDB if not in Redis
            if not data:
                data = self.session_collection.find_one(sort=[("timestamp", -1)])
                if data:
                    if '_id' in data:
                        del data['_id']
                    logger.info("Loaded session state from MongoDB")

            if data:
                # 3. Reconstruct Portfolio object
                return Portfolio(**data)
            
            return None
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return None

    # ===== Position Management (Deprecated/No-op/Via Session) =====
    
    def save_position(self, position: Position) -> bool:
        """
        Save or update a position in MongoDB.
        NOTE: With the single-collection model, individual position saving is 
        less relevant if we are syncing the full portfolio state via save_session.
        However, if granular updates are needed, they would need to update the latest session doc.
        For now, this is a no-op or logs a warning to prefer sync_portfolio_to_db.
        """
        logger.warning("save_position is deprecated in single-collection mode. Use sync_portfolio_to_db instead.")
        return True
    
    def save_positions_bulk(self, positions: List[Position]) -> bool:
        """Save multiple positions in a single operation."""
        logger.warning("save_positions_bulk is deprecated in single-collection mode. Use sync_portfolio_to_db instead.")
        return True
    
    def delete_position(self, position_id: str) -> bool:
        """Delete a position from MongoDB (when fully closed)."""
        logger.warning("delete_position is deprecated in single-collection mode. Use sync_portfolio_to_db instead.")
        return True
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Retrieve all open positions for this user/strategy."""
        portfolio = self.load_session()
        if portfolio:
            all_positions = []
            for symbol, lots in portfolio.positions.items():
                all_positions.extend([lot.model_dump() for lot in lots])
            return all_positions
        return []
    
    # ===== Trade Management (Via Session) =====
    
    def save_trade(self, trade: Trade) -> bool:
        """
        Save a completed trade to MongoDB.
        NOTE: Deprecated in favor of full portfolio sync.
        """
        logger.warning("save_trade is deprecated in single-collection mode. Use sync_portfolio_to_db instead.")
        return True
    
    def save_trades_bulk(self, trades: List[Trade]) -> bool:
        """Save multiple trades in a single operation."""
        logger.warning("save_trades_bulk is deprecated in single-collection mode. Use sync_portfolio_to_db instead.")
        return True
    
    def get_all_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve all trades for this user/strategy, ordered by exit time."""
        portfolio = self.load_session()
        if portfolio:
            trades = [t.model_dump() for t in portfolio.trades]
            trades.sort(key=lambda x: x.get('exit_time', ''), reverse=True)
            if limit:
                return trades[:limit]
            return trades
        return []
    
    def get_trades_by_symbol(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve trades for a specific symbol."""
        portfolio = self.load_session()
        if portfolio:
            trades = [t.model_dump() for t in portfolio.trades if t.symbol == symbol]
            trades.sort(key=lambda x: x.get('exit_time', ''), reverse=True)
            if limit:
                return trades[:limit]
            return trades
        return []
    
    def get_trade_statistics(self) -> Dict[str, Any]:
        """Calculate aggregate statistics from saved trades."""
        portfolio = self.load_session()
        if not portfolio:
            return {}
            
        trades = portfolio.trades
        total_trades = len(trades)
        if total_trades == 0:
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
            
        total_pnl = sum(t.pnl for t in trades)
        avg_pnl = total_pnl / total_trades
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        return {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / total_trades * 100),
            "max_win": max((t.pnl for t in trades), default=0),
            "max_loss": min((t.pnl for t in trades), default=0),
        }
    
    # ===== Portfolio State Management =====
    
    def save_portfolio_snapshot(self, portfolio: Portfolio, current_prices: Dict[str, float] = None) -> bool:
        """
        Save a snapshot of the entire portfolio state.
        In the single-collection model, `save_session` acts as the snapshot saver.
        """
        return self.save_session(portfolio)
    
    def get_portfolio_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve portfolio snapshots for historical analysis."""
        try:
            cursor = self.session_collection.find({}).sort("timestamp", -1).limit(limit)
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
        """
        # Since everything is in one collection now, we just save the session
        return self.save_session(portfolio)
    
    # ===== Cleanup =====
    
    def clear_all_data(self) -> bool:
        """Clear all data for this user/strategy (use with caution!)."""
        try:
            self.session_collection.delete_many({})
            logger.warning(f"Cleared all data for user {self.user_id}, strategy {self.strategy_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            return False