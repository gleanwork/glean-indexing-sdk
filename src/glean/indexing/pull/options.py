"""Options and auth helpers for source-side pull operations."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


class AuthProvider(Protocol):
    """Provides headers for source API requests."""

    def headers(self) -> Mapping[str, str]:
        """Return headers to merge into a source API request."""
        ...


@dataclass(frozen=True)
class BearerTokenAuth:
    """Bearer token auth provider for source APIs."""

    token: str
    header_name: str = "Authorization"

    def headers(self) -> Mapping[str, str]:
        """Return the bearer authorization header."""
        return {self.header_name: f"Bearer {self.token}"}


@dataclass(frozen=True)
class ApiKeyAuth:
    """API key auth provider for source APIs."""

    key: str
    header_name: str = "Authorization"
    prefix: str | None = None

    def headers(self) -> Mapping[str, str]:
        """Return an API key header."""
        value = f"{self.prefix} {self.key}" if self.prefix else self.key
        return {self.header_name: value}


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


@dataclass
class PullOptions:
    """Default behavior for a source API client."""

    timeout_seconds: float = 30.0
    retries: PullRetryOptions = field(default_factory=PullRetryOptions)
    mask_logs: bool = False
    follow_redirects: bool = True
