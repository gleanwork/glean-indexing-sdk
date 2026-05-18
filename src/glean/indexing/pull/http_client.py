"""Generic source-side HTTP client for indexing connectors."""

import logging
import random
import time
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from glean.indexing.pull.options import AuthProvider, PullOptions
from glean.indexing.pull.rate_limit import NoopRateLimiter, RateLimiter
from glean.indexing.pull.response import PullResponse

logger = logging.getLogger(__name__)

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class PullHttpError(RuntimeError):
    """Raised when a source API request fails."""

    def __init__(self, message: str, *, response: httpx.Response | None = None):
        """Initialize the error."""
        super().__init__(message)
        self.response = response
        self.status_code = response.status_code if response is not None else None


class PullHttpClient:
    """HTTP client for source APIs.

    This is the SDK equivalent of Conduit's APILibrary mechanics: session reuse,
    base URL handling, auth/header injection, retries, rate limiting, parsing,
    and bounded binary fetches. Endpoint semantics remain connector-specific.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        auth: AuthProvider | None = None,
        options: PullOptions | None = None,
        rate_limiter: RateLimiter | None = None,
        client: httpx.Client | None = None,
    ):
        """Initialize the source API client."""
        self.base_url = base_url.rstrip("/") + "/"
        self.default_headers = dict(headers or {})
        self.auth = auth
        self.options = options or PullOptions()
        self.rate_limiter = rate_limiter or NoopRateLimiter()
        self._client = client or httpx.Client(follow_redirects=self.options.follow_redirects)
        self._owns_client = client is None

    def close(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PullHttpClient":
        """Enter a context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close on context manager exit."""
        self.close()

    def get(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> PullResponse:
        """Issue a GET request and parse the response."""
        return self.request(
            "GET", path_or_url, params=params, headers=headers, timeout_seconds=timeout_seconds
        )

    def post(
        self,
        path_or_url: str,
        *,
        json: Any = None,
        data: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> PullResponse:
        """Issue a POST request and parse the response."""
        return self.request(
            "POST",
            path_or_url,
            json=json,
            data=data,
            params=params,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )

    def put(
        self,
        path_or_url: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> PullResponse:
        """Issue a PUT request and parse the response."""
        return self.request(
            "PUT",
            path_or_url,
            json=json,
            data=data,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )

    def request(
        self,
        method: HttpMethod,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> PullResponse:
        """Issue an HTTP request with retry and rate limiting."""
        response = self._request_raw(
            method,
            path_or_url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        return self._parse_response(response)

    def get_bytes(
        self,
        path_or_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
    ) -> tuple[bytes, str]:
        """Fetch raw bytes with an optional size cap."""
        response = self._request_raw(
            "GET", path_or_url, headers=headers, timeout_seconds=timeout_seconds
        )
        content = response.content if max_bytes is None else response.content[:max_bytes]
        if max_bytes is not None and len(response.content) > max_bytes:
            logger.warning("Downloaded content was truncated to %s bytes", max_bytes)
        return content, response.headers.get("content-type", "")

    def _request_raw(
        self,
        method: HttpMethod,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> httpx.Response:
        url = self._full_url(path_or_url)
        request_headers = self._headers(headers)
        retry_options = self.options.retries
        attempts = max(1, retry_options.max_attempts)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self.rate_limiter.acquire()
            try:
                logger.info(
                    "Pull %s %s params=%s",
                    method,
                    url,
                    "***MASKED***" if self.options.mask_logs else params,
                )
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=request_headers,
                    timeout=timeout_seconds or self.options.timeout_seconds,
                )
                if response.status_code not in retry_options.retry_status_codes:
                    response.raise_for_status()
                    return response
                last_error = PullHttpError(
                    f"Retryable source API status {response.status_code}", response=response
                )
            except httpx.HTTPStatusError as exc:
                raise PullHttpError(
                    f"Source API request failed with status {exc.response.status_code}",
                    response=exc.response,
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if not retry_options.retry_connection_errors:
                    raise PullHttpError(f"Source API request failed: {exc}") from exc

            if attempt == attempts:
                break
            self._sleep_before_retry(attempt, response if "response" in locals() else None)

        if isinstance(last_error, PullHttpError):
            raise last_error
        raise PullHttpError(f"Source API request failed after {attempts} attempts: {last_error}")

    def _sleep_before_retry(self, attempt: int, response: httpx.Response | None) -> None:
        retry_options = self.options.retries
        if retry_options.respect_retry_after and response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    time.sleep(float(retry_after))
                    return
                except ValueError:
                    pass

        sleep_seconds = min(
            retry_options.max_backoff_seconds,
            retry_options.initial_backoff_seconds
            * retry_options.backoff_multiplier ** (attempt - 1),
        )
        time.sleep(sleep_seconds + random.uniform(0, 0.1))

    def _parse_response(self, response: httpx.Response) -> PullResponse:
        content_type = response.headers.get("content-type", "")
        data: Any = None
        content: bytes | None = response.content or None
        if response.content and "json" in content_type:
            data = response.json()
        elif response.content and _is_text(content_type):
            data = response.text
        return PullResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            url=str(response.url),
            data=data,
            content=content,
        )

    def _headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        out = dict(self.default_headers)
        if self.auth is not None:
            out.update(self.auth.headers())
        if headers:
            out.update(headers)
        return out

    def _full_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urljoin(self.base_url, path_or_url.lstrip("/"))


def _is_text(content_type: str) -> bool:
    return content_type.startswith("text/") or "xml" in content_type or "html" in content_type
