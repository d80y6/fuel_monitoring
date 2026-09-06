"""
Circuit Breaker

This module provides the CircuitBreaker class for preventing repeated failures.
"""
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = 1  # Normal operation, requests allowed
    OPEN = 2    # Failure threshold exceeded, requests blocked
    HALF_OPEN = 3  # Recovery period, limited requests allowed

class CircuitBreaker:
    """
    Circuit breaker to prevent repeated failures.
    
    Tracks failures and blocks requests when a threshold is exceeded.
    """
    
    def __init__(self, name, failure_threshold=3, recovery_timeout=30):
        """
        Initialize the circuit breaker.
        
        Args:
            name: Name of the circuit breaker
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before allowing retry
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_success_time = time.time()
    
    def allow_request(self):
        """
        Check if a request should be allowed.
        
        Returns:
            bool: True if request is allowed, False otherwise
        """
        current_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
            
        elif self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if current_time - self.last_failure_time > self.recovery_timeout:
                logger.info(f"Circuit {self.name} transitioning from OPEN to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
            
        elif self.state == CircuitState.HALF_OPEN:
            # In half-open state, allow one request to test recovery
            return True
    
    def on_success(self):
        """Record a successful request."""
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # On success in half-open state, close the circuit
            logger.info(f"Circuit {self.name} transitioning from HALF_OPEN to CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
        
        # Reset failure count on success
        self.failure_count = 0
    
    def on_failure(self):
        """Record a failed request."""
        current_time = time.time()
        self.last_failure_time = current_time
        
        if self.state == CircuitState.CLOSED:
            # Increment failure count
            self.failure_count += 1
            
            # Check if threshold is exceeded
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Circuit {self.name} transitioning from CLOSED to OPEN after {self.failure_count} failures")
                self.state = CircuitState.OPEN
                
        elif self.state == CircuitState.HALF_OPEN:
            # On failure in half-open state, reopen the circuit
            logger.warning(f"Circuit {self.name} transitioning from HALF_OPEN to OPEN after failure")
            self.state = CircuitState.OPEN
            self.failure_count = self.failure_threshold
    
    def reset(self):
        """Reset the circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_success_time = time.time()
        logger.info(f"Circuit {self.name} manually reset to CLOSED state")
