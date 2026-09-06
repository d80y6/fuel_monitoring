"""
Redis-based sliding window rate limiter.

Uses Redis sorted sets to implement a sliding window algorithm.
Each key stores timestamps of requests; expired entries are pruned on access.
"""
import time
import logging
from functools import wraps
from flask import request, jsonify, g
from redis import Redis, ConnectionPool

logger = logging.getLogger(__name__)

# Module-level connection pool (shared across the app)
_pool = None
_redis = None


def init_rate_limiter(app):
    """Initialize the Redis connection for the rate limiter.

    Called once at app startup.  Reads REDIS_URL from the Flask config.
    Falls back gracefully when Redis is unavailable (all checks pass).
    """
    global _pool, _redis
    try:
        redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        _pool = ConnectionPool.from_url(redis_url, decode_responses=True)
        _redis = Redis(connection_pool=_pool, socket_timeout=2)
        _redis.ping()
        logger.info("Rate limiter connected to Redis")
    except Exception as e:
        logger.warning("Rate limiter running without Redis: %s", e)
        _redis = None


def _get_redis():
    return _redis


class SlidingWindowRateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets.

    Parameters
    ----------
    max_requests : int
        Maximum number of requests allowed in the window.
    window_seconds : int
        Duration of the sliding window in seconds.
    key_prefix : str
        Prefix prepended to every Redis key (for namespacing).
    """

    def __init__(self, max_requests: int, window_seconds: int, key_prefix: str = "rl"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def _build_key(self, identifier: str) -> str:
        return f"{self.key_prefix}:{identifier}"

    def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """Check whether *identifier* is within the rate limit.

        Returns
        -------
        (allowed, info) where *info* contains rate-limit headers.
        """
        redis = _get_redis()
        now = time.time()
        window_start = now - self.window_seconds
        key = self._build_key(identifier)

        if redis is None:
            # No Redis — allow everything (fail-open for availability).
            return True, {
                'X-RateLimit-Limit': self.max_requests,
                'X-RateLimit-Remaining': self.max_requests,
                'X-RateLimit-Reset': int(now + self.window_seconds),
            }

        pipe = redis.pipeline()
        # Remove entries outside the window.
        pipe.zremrangebyscore(key, 0, window_start)
        # Count remaining entries.
        pipe.zcard(key)
        # Add the current request.
        pipe.zadd(key, {f"{now}": now})
        # Set expiry on the key so it eventually gets cleaned up.
        pipe.expire(key, self.window_seconds)
        _, current_count, _, _ = pipe.execute()

        remaining = max(0, self.max_requests - current_count)
        reset_at = int(now + self.window_seconds)

        headers = {
            'X-RateLimit-Limit': self.max_requests,
            'X-RateLimit-Remaining': remaining,
            'X-RateLimit-Reset': reset_at,
        }

        if current_count > self.max_requests:
            # Remove the entry we just added because we're over limit.
            redis.zrem(key, f"{now}")
            return False, headers

        return True, headers

    def reset(self, identifier: str):
        """Reset the window for *identifier* (e.g. after a successful login)."""
        redis = _get_redis()
        if redis:
            redis.delete(self._build_key(identifier))


# ---------------------------------------------------------------------------
# Pre-configured limiters
# ---------------------------------------------------------------------------

# Login: 5 attempts per 15 minutes per IP.
login_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=900, key_prefix="rl:login")

# Password reset: 3 requests per hour per IP.
password_reset_limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=3600, key_prefix="rl:pwreset")

# General API: 60 requests per minute per user.
api_limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60, key_prefix="rl:api")


def rate_limit(limiter: SlidingWindowRateLimiter, key_func=None):
    """Decorator that applies a *limiter* to a Flask route.

    *key_func(request)* should return the identifier string (default: client IP).
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if key_func:
                identifier = key_func(request)
            else:
                identifier = request.remote_addr or "unknown"

            allowed, headers = limiter.is_allowed(identifier)

            # Attach headers so @app.after_request can add them to the response.
            g.rate_limit_headers = headers

            if not allowed:
                return jsonify({
                    'error': 'Too many requests. Please try again later.',
                    'retry_after': headers['X-RateLimit-Reset'] - int(time.time()),
                }), 429

            return f(*args, **kwargs)

        return wrapped
    return decorator
