"""
Redis cache connection and utilities.
Falls back to in-memory cache if Redis is unavailable.
"""
import redis
import json
import logging
import time
from typing import Any, Optional, Union
from datetime import timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Simple in-memory cache fallback when Redis is unavailable."""

    def __init__(self):
        self._cache = {}
        self._expiry = {}

    def set(self, key: str, value: str, ex: int = None) -> bool:
        self._cache[key] = value
        if ex:
            self._expiry[key] = time.time() + ex
        return True

    def setex(self, key: str, seconds: int, value: str) -> bool:
        self._cache[key] = value
        self._expiry[key] = time.time() + seconds
        return True

    def get(self, key: str) -> Optional[str]:
        # Check expiry
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._cache[key]
            del self._expiry[key]
            return None
        return self._cache.get(key)

    def delete(self, key: str) -> int:
        if key in self._cache:
            del self._cache[key]
            self._expiry.pop(key, None)
            return 1
        return 0

    def exists(self, key: str) -> int:
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._cache[key]
            del self._expiry[key]
            return 0
        return 1 if key in self._cache else 0

    def ping(self) -> bool:
        return True


class RedisCache:
    """Redis cache wrapper with JSON serialization. Falls back to in-memory if Redis unavailable."""

    def __init__(self):
        self.redis_client = None
        self.using_fallback = False
        self.connect()

    def connect(self):
        """Establish Redis connection, fall back to in-memory if unavailable."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            self.using_fallback = False
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using in-memory cache fallback")
            self.redis_client = InMemoryCache()
            self.using_fallback = True
    
    def set(self, key: str, value: Any, expiration: Optional[Union[int, timedelta]] = None) -> bool:
        """Set a value in Redis with optional expiration."""
        if not self.redis_client:
            logger.warning("Redis client not available")
            return False
        
        try:
            # Convert value to JSON string
            json_value = json.dumps(value, default=str)
            
            if expiration:
                if isinstance(expiration, timedelta):
                    expiration = int(expiration.total_seconds())
                return self.redis_client.setex(key, expiration, json_value)
            else:
                return self.redis_client.set(key, json_value)
                
        except Exception as e:
            logger.error(f"Failed to set Redis key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis."""
        if not self.redis_client:
            logger.warning("Redis client not available")
            return None
        
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            # Parse JSON string back to Python object
            return json.loads(value)
            
        except Exception as e:
            logger.error(f"Failed to get Redis key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self.redis_client:
            return False
        
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete Redis key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        if not self.redis_client:
            return False
        
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Failed to check Redis key {key}: {e}")
            return False
    
    def set_market_data(self, symbol: str, timeframe: str, data: dict, expiration: int = 300):
        """Store market data with 5-minute default expiration."""
        key = f"market_data:{symbol}:{timeframe}"
        return self.set(key, data, expiration)
    
    def get_market_data(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Get cached market data."""
        key = f"market_data:{symbol}:{timeframe}"
        return self.get(key)
    
    def set_position(self, symbol: str, position_data: dict):
        """Store current position data."""
        key = f"position:{symbol}"
        return self.set(key, position_data)
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position data."""
        key = f"position:{symbol}"
        return self.get(key)
    
    def health_check(self) -> bool:
        """Check Redis health."""
        try:
            if self.redis_client:
                self.redis_client.ping()
                return True
            return False
        except Exception:
            return False

    def is_using_fallback(self) -> bool:
        """Check if using in-memory fallback instead of Redis."""
        return self.using_fallback


# Create global Redis cache instance
redis_cache = RedisCache()