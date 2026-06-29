"""Rate limiting helpers for source-side pull recipes."""

import threading
import time
from collections.abc import Callable
from typing import Protocol


class RateLimitExceededError(RuntimeError):
    """Raised when rate-limit capacity is not available before timeout."""


class RateLimiter(Protocol):
    """Rate limiter interface used by pull HTTP clients."""

    def acquire(self, tokens: float = 1.0, timeout_seconds: float | None = None) -> None:
        """Block until capacity is available or raise `RateLimitExceededError`."""
        ...


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Tokens refill continuously at `rate_per_second` up to `capacity`. Each
    request consumes one token by default.
    """

    def __init__(
        self,
        *,
        rate_per_second: float,
        capacity: float,
        initial_tokens: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the token bucket.

        Args:
            rate_per_second: Token refill rate.
            capacity: Maximum tokens the bucket can hold.
            initial_tokens: Initial token count. Defaults to full capacity.
            clock: Monotonic clock function.
            sleep: Sleep function used while waiting for capacity.
        """
        if rate_per_second <= 0:
            msg = "rate_per_second must be greater than zero"
            raise ValueError(msg)
        if capacity <= 0:
            msg = "capacity must be greater than zero"
            raise ValueError(msg)

        self.rate_per_second = rate_per_second
        self.capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = capacity if initial_tokens is None else min(max(0.0, initial_tokens), capacity)
        self._last_refill = self._clock()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0, timeout_seconds: float | None = None) -> None:
        """Block until `tokens` are available.

        Args:
            tokens: Number of tokens to consume.
            timeout_seconds: Maximum time to wait for capacity. `None` waits indefinitely.
        """
        if tokens <= 0:
            msg = "tokens must be greater than zero"
            raise ValueError(msg)
        if tokens > self.capacity:
            msg = "tokens cannot be greater than capacity"
            raise ValueError(msg)
        if timeout_seconds is not None and timeout_seconds < 0:
            msg = "timeout_seconds must be non-negative"
            raise ValueError(msg)

        start = self._clock()
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait_seconds = (tokens - self._tokens) / self.rate_per_second

            if timeout_seconds is not None:
                elapsed = self._clock() - start
                if elapsed + wait_seconds > timeout_seconds:
                    raise RateLimitExceededError("Rate limit capacity was not available before timeout")

            self._sleep(wait_seconds)

    def _refill_locked(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed == 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)
        self._last_refill = now
