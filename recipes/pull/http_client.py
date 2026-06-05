"""Generic source-side HTTP client for connector data clients."""

import logging
import random
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from recipes.pull.options import PullOptions
from recipes.pull.response import PullResponse

logger = logging.getLogger(__name__)

HttpMethod = Literal["GET", "POST"]


class PullHttpError(RuntimeError):
    """Raised when a source API request fails."""

    def __init__(self, message: str, *, response: httpx.Response | None = None) -> None:
        """Initialize the source HTTP error."""
        super().__init__(message)
        self.response = response
        self.status_code = response.status_code if response is not None else None


class PullHttpClient:
    """HTTP client recipe for source APIs.

    It provides session reuse, base URL handling, header merging, retries,
    response parsing, redacted request logging, and bounded binary fetches.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        options: PullOptions | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the source API client.

        Args:
            base_url: Base URL for relative request paths.
            headers: Default headers sent with each request.
            options: Request timeout, retry, redirect, and logging behavior.
            client: Optional preconfigured `httpx.Client`.
            sleep: Sleep function used for retry backoff.
        """
        self.base_url = base_url.rstrip("/") + "/"
        self.default_headers = dict(headers or {})
        self.options = options or PullOptions()
        self._client = client or httpx.Client(follow_redirects=self.options.follow_redirects)
        self._owns_client = client is None
        self._sleep = sleep

    def close(self) -> None:
        """Close the underlying HTTP client if this recipe owns it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PullHttpClient":
        """Enter a context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the client on context manager exit."""
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
        return self.request("GET", path_or_url, params=params, headers=headers, timeout_seconds=timeout_seconds)

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
        """Issue an HTTP request with retry handling."""
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

    def paginate(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        next_page: Callable[[PullResponse], str | None] | None = None,
    ) -> Iterator[PullResponse]:
        """Yield GET responses across pages.

        By default, follows RFC 5988 `Link` headers with `rel="next"`.
        Streaming data clients can iterate over responses and yield items from each page.
        """
        current_path: str | None = path_or_url
        current_params = params
        resolve_next_page = next_page or _next_link_url

        while current_path:
            response = self.get(current_path, params=current_params, headers=headers, timeout_seconds=timeout_seconds)
            yield response

            current_path = resolve_next_page(response)
            current_params = None

    def get_bytes(
        self,
        path_or_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
    ) -> tuple[bytes, str]:
        """Fetch raw bytes with an optional size cap.

        Args:
            path_or_url: Relative path or absolute source URL.
            headers: Optional per-request headers.
            timeout_seconds: Optional timeout override.
            max_bytes: Optional cap for returned bytes.

        Returns:
            A tuple of response bytes and content type.
        """
        response = self._request_raw("GET", path_or_url, headers=headers, timeout_seconds=timeout_seconds)
        content = response.content if max_bytes is None else response.content[:max_bytes]
        if max_bytes is not None and len(response.content) > max_bytes:
            logger.warning("Downloaded source content was truncated to %s bytes", max_bytes)
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
            response: httpx.Response | None = None
            try:
                logger.info("Pull %s %s params=%s", method, url, "***MASKED***" if self.options.mask_logs else params)
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=request_headers,
                    timeout=timeout_seconds if timeout_seconds is not None else self.options.timeout_seconds,
                )
                if response.status_code not in retry_options.retry_status_codes:
                    response.raise_for_status()
                    return response
                last_error = PullHttpError(f"Retryable source API status {response.status_code}", response=response)
            except httpx.HTTPStatusError as exc:
                raise PullHttpError(
                    f"Source API request failed with status {exc.response.status_code}",
                    response=exc.response,
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if not retry_options.retry_connection_errors:
                    raise PullHttpError(f"Source API request failed: {exc}") from exc

            if attempt == attempts:
                break
            self._sleep_before_retry(attempt, response)

        if isinstance(last_error, PullHttpError):
            raise last_error
        raise PullHttpError(f"Source API request failed after {attempts} attempts: {last_error}")

    def _sleep_before_retry(self, attempt: int, response: httpx.Response | None) -> None:
        retry_options = self.options.retries
        if retry_options.respect_retry_after and response is not None:
            retry_after_seconds = _retry_after_seconds(response.headers.get("retry-after"))
            if retry_after_seconds is not None:
                self._sleep(retry_after_seconds)
                return

        sleep_seconds = min(
            retry_options.max_backoff_seconds,
            retry_options.initial_backoff_seconds * retry_options.backoff_multiplier ** (attempt - 1),
        )
        if retry_options.jitter_seconds > 0:
            sleep_seconds += random.uniform(0, retry_options.jitter_seconds)
        self._sleep(sleep_seconds)

    def _parse_response(self, response: httpx.Response) -> PullResponse:
        content_type = response.headers.get("content-type", "")
        data: Any = None
        content: bytes | None = response.content or None

        if response.content and "json" in content_type:
            try:
                data = response.json()
            except ValueError as exc:
                raise PullHttpError("Source API returned invalid JSON", response=response) from exc
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
        if headers:
            out.update(headers)
        return out

    def _full_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urljoin(self.base_url, path_or_url.lstrip("/"))


def _is_text(content_type: str) -> bool:
    return content_type.startswith("text/") or "xml" in content_type or "html" in content_type


def _next_link_url(response: PullResponse) -> str | None:
    return _parse_link_header_next(response.headers.get("link") or response.headers.get("Link"))


def _parse_link_header_next(link_header: str | None) -> str | None:
    if not link_header:
        return None

    for part in link_header.split(","):
        segments = [segment.strip() for segment in part.strip().split(";")]
        if not segments:
            continue

        rel_is_next = any(segment.lower() in {'rel="next"', "rel='next'", "rel=next"} for segment in segments[1:])
        link = segments[0]
        if rel_is_next and link.startswith("<") and ">" in link:
            return link[1 : link.index(">")]

    return None


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
