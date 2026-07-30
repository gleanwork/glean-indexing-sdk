"""Authentication helpers for source-side pull recipes."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from typing import Protocol

import httpx


class OAuth2TokenError(RuntimeError):
    """Raised when OAuth2 token loading, storage, or refresh fails."""


class AuthProvider(Protocol):
    """Provides headers for source API requests."""

    def headers(self) -> Mapping[str, str]:
        """Return headers to merge into a source API request."""
        ...


@dataclass(frozen=True)
class RefreshingBearerTokenAuth:
    """Bearer auth provider backed by an OAuth2 token provider."""

    token_provider: Callable[[], str]

    def headers(self) -> Mapping[str, str]:
        """Return a bearer header using the current OAuth2 access token."""
        return {"Authorization": f"Bearer {self.token_provider()}"}


@dataclass(frozen=True)
class OAuth2Token:
    """OAuth2 token state for source API authentication."""

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None

    def is_expired(self, *, skew_seconds: float = 60.0) -> bool:
        """Return whether the access token should be refreshed."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - skew_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize token state to JSON-compatible data."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
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

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=float(expires_at) if expires_at is not None else None,
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
        token_store: OAuth2TokenStore,
        client_secret: str | None = None,
        client: httpx.Client | None = None,
        extra_token_params: Mapping[str, str] | None = None,
        expiry_skew_seconds: float = 60.0,
    ) -> None:
        """Initialize the provider.

        Args:
            token_url: OAuth2 token endpoint.
            client_id: OAuth2 client ID.
            token_store: Persistent storage for OAuth2 token state.
            client_secret: Optional OAuth2 client secret.
            client: Optional injected HTTP client.
            extra_token_params: Extra form params for provider-specific token endpoints.
            expiry_skew_seconds: Refresh tokens this many seconds before expiry.
        """
        self.token_url = token_url
        self.client_id = client_id
        self.token_store = token_store
        self.client_secret = client_secret
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self.extra_token_params = dict(extra_token_params or {})
        self.expiry_skew_seconds = expiry_skew_seconds
        self._token: OAuth2Token | None = None

    def __call__(self) -> str:
        """Return a valid access token, refreshing or minting as needed."""
        token = self._current_token()
        if token is not None and not token.is_expired(
            skew_seconds=self.expiry_skew_seconds,
        ):
            return token.access_token

        if token is None:
            raise OAuth2TokenError("OAuth2 token store does not contain token state")
        if not token.refresh_token:
            raise OAuth2TokenError("Expired OAuth2 token does not contain a refresh token")

        token = self._fetch_token(refresh_token=token.refresh_token)
        self.token_store.save(token)
        self._token = token
        return token.access_token

    def close(self) -> None:
        """Close the underlying HTTP client if this provider owns it."""
        if self._owns_client:
            self._client.close()

    def _current_token(self) -> OAuth2Token | None:
        if self._token is not None:
            return self._token
        self._token = self.token_store.load()
        return self._token

    def _fetch_token(self, *, refresh_token: str) -> OAuth2Token:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
            **self.extra_token_params,
        }
        if self.client_secret is not None:
            data["client_secret"] = self.client_secret

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

        expires_in = payload.get("expires_in")
        if expires_in is not None and not isinstance(expires_in, (int, float)):
            raise OAuth2TokenError("OAuth2 token endpoint expires_in must be a number")
        expires_at = time.time() + float(expires_in) if expires_in is not None else None

        return OAuth2Token(
            access_token=access_token,
            refresh_token=new_refresh_token or refresh_token,
            expires_at=expires_at,
        )
