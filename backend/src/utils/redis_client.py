import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Try to import redis, fall back to mock if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

class MockRedisClient:
    """Mock Redis client for development when Redis is not available"""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        
    async def connect(self):
        print("✅ Mock Redis client initialized (Redis container not required)")
        
    async def disconnect(self):
        print("📤 Mock Redis client disconnected")
        
    async def ping(self):
        return True
        
    async def hset(self, key: str, mapping: Dict[str, str]):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
        
    async def hgetall(self, key: str) -> Dict[str, str]:
        return self.data.get(key, {})
        
    async def expire(self, key: str, seconds: int):
        # In mock mode, we don't actually expire keys
        pass
        
    async def lpush(self, key: str, value: str):
        if key not in self.data:
            self.data[key] = []
        self.data[key].insert(0, value)
        
    async def ltrim(self, key: str, start: int, end: int):
        if key in self.data and isinstance(self.data[key], list):
            if end == -1:
                self.data[key] = self.data[key][start:]
            else:
                self.data[key] = self.data[key][start:end+1]
                
    async def lrange(self, key: str, start: int, end: int) -> list:
        if key not in self.data or not isinstance(self.data[key], list):
            return []
        if end == -1:
            return self.data[key][start:]
        return self.data[key][start:end+1]
        
    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
            
    async def setex(self, key: str, seconds: int, value: str):
        self.data[key] = value
        
    async def get(self, key: str) -> Optional[str]:
        return self.data.get(key)

class RedisClient:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis = None
        self.use_mock = not REDIS_AVAILABLE or os.getenv("USE_MOCK_REDIS", "false").lower() == "true"
        
    async def connect(self):
        """Connect to Redis or initialize mock"""
        if self.use_mock or not REDIS_AVAILABLE:
            self.redis = MockRedisClient()
            await self.redis.connect()
        else:
            try:
                self.redis = redis.from_url(self.redis_url, decode_responses=True)
                await self.redis.ping()
                print("✅ Connected to Redis server")
            except Exception as e:
                print(f"⚠️ Failed to connect to Redis: {e}. Using mock client.")
                self.redis = MockRedisClient()
                await self.redis.connect()
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            if hasattr(self.redis, 'close'):
                await self.redis.close()
            elif hasattr(self.redis, 'disconnect'):
                await self.redis.disconnect()
            print("📤 Disconnected from Redis")

    async def hset(self, key: str, mapping: Dict[str, Any]):
        """Proxy for the hset command."""
        return await self.redis.hset(key, mapping=mapping)
    
    # Backtest Task Management
    async def set_backtest_status(self, backtest_id: str, status: str, progress: int = 0, **kwargs):
        """Update backtest status in Redis"""
        key = f"backtest:{backtest_id}"
        data = {
            "status": status,
            "progress": progress,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            **kwargs
        }
        await self.redis.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()})
        # Set expiration for 24 hours
        await self.redis.expire(key, 86400)
    
    async def get_backtest_status(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get backtest status from Redis"""
        key = f"backtest:{backtest_id}"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        
        # Parse JSON fields
        for k, v in data.items():
            try:
                data[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string
        
        return data
    
    async def add_backtest_log(self, backtest_id: str, message: str):
        """Add log message to backtest"""
        key = f"backtest:{backtest_id}:logs"
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        log_entry = f"[{timestamp}] {message}"
        await self.redis.lpush(key, log_entry)
        # Keep only last 100 logs
        await self.redis.ltrim(key, 0, 99)
        # Set expiration
        await self.redis.expire(key, 86400)
    
    async def get_backtest_logs(self, backtest_id: str) -> list:
        """Get backtest logs"""
        key = f"backtest:{backtest_id}:logs"
        logs = await self.redis.lrange(key, 0, -1)
        return logs
    
    async def delete_backtest_data(self, backtest_id: str):
        """Clean up backtest data from Redis"""
        keys = [
            f"backtest:{backtest_id}",
            f"backtest:{backtest_id}:logs"
        ]
        await self.redis.delete(*keys)
    
    # General utilities
    async def set_with_ttl(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Set key with TTL"""
        await self.redis.setex(key, ttl_seconds, json.dumps(value) if isinstance(value, (dict, list)) else str(value))
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        value = await self.redis.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    # Rate Limiting
    async def check_rate_limit(self, user_id: str, endpoint: str, limit: int = 60, window: int = 60) -> bool:
        """Check if user has exceeded rate limit"""
        key = f"rate_limit:{user_id}:{endpoint}"
        current = await self.redis.get(key)
        
        if current is None:
            await self.redis.setex(key, window, "1")
            return True
        
        if int(current) >= limit:
            return False
            
        await self.redis.incr(key)
        return True
    
    # Market Data Caching
    async def cache_market_data(self, symbol: str, data: Dict[str, Any], ttl: int = 30):
        """Cache real-time market data"""
        key = f"market:{symbol}"
        await self.redis.setex(key, ttl, json.dumps(data))
    
    async def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached market data"""
        key = f"market:{symbol}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    # Session Management
    async def store_user_session(self, user_id: str, session_data: Dict[str, Any], ttl: int = 3600):
        """Store user session data"""
        key = f"session:{user_id}"
        await self.redis.setex(key, ttl, json.dumps(session_data))
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user session data"""
        key = f"session:{user_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

# Global Redis client instance
redis_client = RedisClient()
