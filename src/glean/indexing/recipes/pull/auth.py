"""Authentication helpers for source-side pull recipes."""

import base64
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from typing import Protocol

import httpx

TokenProvider = Callable[[], str]


class OAuth2TokenError(RuntimeError):
    """Raised when OAuth2 token loading, storage, or refresh fails."""


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


@dataclass(frozen=True)
class OAuth2Token:
    """OAuth2 token state for source API authentication.

    Refresh tokens are secrets. Connector authors should provide an
    `OAuth2TokenStore` backed by storage appropriate for their runtime.
    """

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    token_type: str = "Bearer"
    scopes: tuple[str, ...] = ()

    def is_expired(self, *, now: float | None = None, skew_seconds: float = 60.0) -> bool:
        """Return whether the access token should be refreshed."""
        if self.expires_at is None:
            return False
        current_time = time.time() if now is None else now
        return current_time >= self.expires_at - skew_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize token state to JSON-compatible data."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scopes": list(self.scopes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OAuth2Token":
        """Deserialize token state from JSON-compatible data."""
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuth2TokenError("Stored OAuth2 token is missing access_token")

        refresh_token = data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise OAuth2TokenError("Stored OAuth2 token refresh_token must be a string")

        expires_at = data.get("expires_at")
        if expires_at is not None and not isinstance(expires_at, (int, float)):
            raise OAuth2TokenError("Stored OAuth2 token expires_at must be a number")

        token_type = data.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type:
            raise OAuth2TokenError("Stored OAuth2 token token_type must be a non-empty string")

        scopes_value = data.get("scopes", [])
        if isinstance(scopes_value, str):
            scopes = tuple(scope for scope in scopes_value.split() if scope)
        elif isinstance(scopes_value, Sequence):
            scopes = tuple(scope for scope in scopes_value if isinstance(scope, str) and scope)
        else:
            raise OAuth2TokenError("Stored OAuth2 token scopes must be a list or string")

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=float(expires_at) if expires_at is not None else None,
            token_type=token_type,
            scopes=scopes,
        )


class OAuth2TokenStore(Protocol):
    """Storage interface for OAuth2 token state."""

    def load(self) -> OAuth2Token | None:
        """Load token state, if present."""
        ...

    def save(self, token: OAuth2Token) -> None:
        """Persist token state."""
        ...


class OAuth2TokenProvider:
    """Callable OAuth2 access-token provider with refresh support."""

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str | None = None,
        scopes: Sequence[str] | None = None,
        refresh_token: str | None = None,
        token_store: OAuth2TokenStore | None = None,
        client: httpx.Client | None = None,
        extra_token_params: Mapping[str, str] | None = None,
        expiry_skew_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialize the provider.

        Args:
            token_url: OAuth2 token endpoint.
            client_id: OAuth2 client ID.
            client_secret: Optional OAuth2 client secret.
            scopes: Optional requested scopes.
            refresh_token: Optional bootstrap refresh token.
            token_store: Optional persistent token storage.
            client: Optional injected HTTP client.
            extra_token_params: Extra form params for provider-specific token endpoints.
            expiry_skew_seconds: Refresh tokens this many seconds before expiry.
            clock: Clock used for expiry calculations.
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = tuple(scopes or ())
        self.refresh_token = refresh_token
        self.token_store = token_store
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self.extra_token_params = dict(extra_token_params or {})
        self.expiry_skew_seconds = expiry_skew_seconds
        self._clock = clock
        self._token: OAuth2Token | None = None

    def __call__(self) -> str:
        """Return a valid access token, refreshing or minting as needed."""
        token = self._current_token()
        if token is not None and not token.is_expired(
            now=self._clock(),
            skew_seconds=self.expiry_skew_seconds,
        ):
            return token.access_token

        refresh_token = (token.refresh_token if token else None) or self.refresh_token
        if refresh_token:
            token = self._fetch_token("refresh_token", refresh_token=refresh_token)
        else:
            token = self._fetch_token("client_credentials")

        self._token = token
        if self.token_store is not None:
            self.token_store.save(token)
        return token.access_token

    def close(self) -> None:
        """Close the underlying HTTP client if this provider owns it."""
        if self._owns_client:
            self._client.close()

    def _current_token(self) -> OAuth2Token | None:
        if self._token is not None:
            return self._token
        if self.token_store is None:
            return None
        self._token = self.token_store.load()
        return self._token

    def _fetch_token(self, grant_type: str, *, refresh_token: str | None = None) -> OAuth2Token:
        data = {
            "grant_type": grant_type,
            "client_id": self.client_id,
            **self.extra_token_params,
        }
        if self.client_secret is not None:
            data["client_secret"] = self.client_secret
        if self.scopes:
            data["scope"] = " ".join(self.scopes)
        if refresh_token is not None:
            data["refresh_token"] = refresh_token

        try:
            response = self._client.post(self.token_url, data=data)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OAuth2TokenError(f"OAuth2 token request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuth2TokenError("OAuth2 token endpoint returned invalid JSON") from exc

        if not isinstance(payload, Mapping):
            raise OAuth2TokenError("OAuth2 token endpoint response must be a JSON object")

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuth2TokenError("OAuth2 token endpoint response is missing access_token")

        new_refresh_token = payload.get("refresh_token")
        if new_refresh_token is not None and not isinstance(new_refresh_token, str):
            raise OAuth2TokenError("OAuth2 token endpoint refresh_token must be a string")

        token_type = payload.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type:
            raise OAuth2TokenError("OAuth2 token endpoint token_type must be a non-empty string")

        expires_in = payload.get("expires_in")
        if expires_in is not None and not isinstance(expires_in, (int, float)):
            raise OAuth2TokenError("OAuth2 token endpoint expires_in must be a number")
        expires_at = self._clock() + float(expires_in) if expires_in is not None else None

        response_scope = payload.get("scope")
        if isinstance(response_scope, str):
            scopes = tuple(scope for scope in response_scope.split() if scope)
        else:
            scopes = self.scopes

        return OAuth2Token(
            access_token=access_token,
            refresh_token=new_refresh_token or refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            scopes=scopes,
        )
