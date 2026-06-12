"""Authentication helpers for source-side pull recipes."""

import base64
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

TokenProvider = Callable[[], str]


class AuthProvider(Protocol):
    """Provides headers for source API requests."""

    def headers(self) -> Mapping[str, str]:
        """Return headers to merge into a source API request."""
        ...


@dataclass(frozen=True)
class BearerTokenAuth:
    """Bearer token auth provider for PATs and already-issued OAuth tokens."""

    token: str
    header_name: str = "Authorization"
    scheme: str = "Bearer"

    def headers(self) -> Mapping[str, str]:
        """Return the bearer authorization header."""
        return {self.header_name: f"{self.scheme} {self.token}"}


@dataclass(frozen=True)
class ApiKeyAuth:
    """API key auth provider for source APIs."""

    key: str
    header_name: str
    prefix: str | None = None

    def headers(self) -> Mapping[str, str]:
        """Return an API key header."""
        value = f"{self.prefix} {self.key}" if self.prefix else self.key
        return {self.header_name: value}


@dataclass(frozen=True)
class BasicAuth:
    """HTTP Basic auth provider for source APIs."""

    username: str
    password: str
    header_name: str = "Authorization"

    def headers(self) -> Mapping[str, str]:
        """Return the Basic authorization header."""
        credentials = f"{self.username}:{self.password}".encode()
        token = base64.b64encode(credentials).decode()
        return {self.header_name: f"Basic {token}"}


@dataclass(frozen=True)
class RefreshingBearerTokenAuth:
    """Bearer auth provider backed by datasource-specific token refresh logic."""

    token_provider: TokenProvider
    header_name: str = "Authorization"
    scheme: str = "Bearer"

    def headers(self) -> Mapping[str, str]:
        """Return a bearer header using the current token from the provider."""
        return {self.header_name: f"{self.scheme} {self.token_provider()}"}
