"""Options for source-side HTTP pull recipes."""

from dataclasses import dataclass, field


@dataclass
class PullRetryOptions:
    """Retry behavior for source API calls."""

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    retry_status_codes: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    retry_connection_errors: bool = True
    respect_retry_after: bool = True
    jitter_seconds: float = 0.1


@dataclass
class PullOptions:
    """Default behavior for a source API HTTP client."""

    timeout_seconds: float = 30.0
    retries: PullRetryOptions = field(default_factory=PullRetryOptions)
    mask_logs: bool = False
    follow_redirects: bool = True
