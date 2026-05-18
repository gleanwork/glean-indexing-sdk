"""Source API rate limiting primitives."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")


class RateLimitExceededError(RuntimeError):
    """Raised when a rate limiter cannot acquire capacity before timeout."""


class RateLimiter:
    """Interface for source API rate limiters."""

    def acquire(self, weight: int = 1, timeout_seconds: float | None = None) -> None:
        """Block until capacity is available or raise `RateLimitExceededError`."""
        raise NotImplementedError

    def wrap(
        self, func: Callable[_P, _R], *, weight: int = 1, timeout_seconds: float | None = None
    ) -> Callable[_P, _R]:
        """Wrap a callable with rate-limit acquisition."""

        @wraps(func)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            self.acquire(weight=weight, timeout_seconds=timeout_seconds)
            return func(*args, **kwargs)

        return wrapped


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for a source API rate limiter."""

    calls: int
    period_seconds: float
    strategy: str = "fixed"

    def create_limiter(self) -> RateLimiter:
        """Create a limiter for this config."""
        if self.strategy.lower() == "rolling":
            return RollingWindowRateLimiter(self.calls, self.period_seconds)
        return FixedWindowRateLimiter(self.calls, self.period_seconds)


class NoopRateLimiter(RateLimiter):
    """Rate limiter that never throttles."""

    def acquire(self, weight: int = 1, timeout_seconds: float | None = None) -> None:
        """Return immediately."""
        return None


class FixedWindowRateLimiter(RateLimiter):
    """Thread-safe fixed-window source API rate limiter."""

    def __init__(self, calls: int, period_seconds: float):
        """Initialize a fixed-window limiter."""
        if calls <= 0:
            raise ValueError("calls must be greater than zero")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be greater than zero")
        self.calls = calls
        self.period_seconds = period_seconds
        self._window_start = time.monotonic()
        self._counter = 0
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1, timeout_seconds: float | None = None) -> None:
        """Block until the fixed window has capacity."""
        weight = max(1, weight)
        start = time.monotonic()
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._window_start + self.period_seconds:
                    self._window_start = now
                    self._counter = 0
                if self._counter + weight <= self.calls:
                    self._counter += weight
                    return
                wait_seconds = max(0.01, self._window_start + self.period_seconds - now)
            _sleep_or_raise(start, wait_seconds, timeout_seconds)


class RollingWindowRateLimiter(RateLimiter):
    """Thread-safe rolling-window source API rate limiter."""

    def __init__(self, calls: int, period_seconds: float):
        """Initialize a rolling-window limiter."""
        if calls <= 0:
            raise ValueError("calls must be greater than zero")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be greater than zero")
        self.calls = calls
        self.period_seconds = period_seconds
        self._request_times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1, timeout_seconds: float | None = None) -> None:
        """Block until the rolling window has capacity."""
        weight = max(1, weight)
        start = time.monotonic()
        while True:
            with self._lock:
                now = time.monotonic()
                while self._request_times and self._request_times[0] <= now - self.period_seconds:
                    self._request_times.popleft()
                if len(self._request_times) + weight <= self.calls:
                    for _ in range(weight):
                        self._request_times.append(now)
                    return
                wait_seconds = max(0.01, self._request_times[0] + self.period_seconds - now)
            _sleep_or_raise(start, wait_seconds, timeout_seconds)


def _sleep_or_raise(start: float, wait_seconds: float, timeout_seconds: float | None) -> None:
    if timeout_seconds is not None and time.monotonic() - start + wait_seconds > timeout_seconds:
        raise RateLimitExceededError("Rate limit capacity was not available before timeout")
    time.sleep(wait_seconds)
