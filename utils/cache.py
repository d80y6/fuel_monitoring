"""Cache utilities for the Fuel Monitoring Platform."""
import json
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, dict] = {}
        self._lock = __import__('threading').Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None if expired or not found."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry['expires_at']:
                del self._cache[key]
                return None
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Set a value in cache with TTL."""
        with self._lock:
            if len(self._cache) >= self.max_size:
                oldest = min(self._cache.items(), key=lambda x: x[1]['created_at'])
                del self._cache[oldest[0]]
            self._cache[key] = {
                'value': value,
                'created_at': time.time(),
                'expires_at': time.time() + (ttl or self.default_ttl),
            }
    
    def delete(self, key: str):
        """Delete a key from cache."""
        with self._lock:
            self._cache.pop(key, None)
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate keys matching a pattern."""
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for k in keys_to_delete:
                del self._cache[k]
    
    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for v in self._cache.values() if v['expires_at'] > now)
            expired = len(self._cache) - valid
            return {
                'size': len(self._cache),
                'valid': valid,
                'expired': expired,
                'max_size': self.max_size,
            }

tank_cache = LRUCache(max_size=5000, default_ttl=300)

def get_cached_tank(tank_id: int) -> Optional[dict]:
    """Get cached tank data."""
    return tank_cache.get(f"tank:{tank_id}")

def cache_tank(tank_id: int, tank_data: dict, ttl: int = 300):
    """Cache tank data."""
    tank_cache.set(f"tank:{tank_id}", tank_data, ttl)

def invalidate_tank_cache(tank_id: int = None):
    """Invalidate tank cache."""
    if tank_id:
        tank_cache.delete(f"tank:{tank_id}")
    else:
        tank_cache.invalidate_pattern("tank:")
