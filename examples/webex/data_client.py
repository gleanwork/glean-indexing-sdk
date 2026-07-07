"""Webex source-side data client.

Fetches spaces and their messages from the Webex REST API and yields them as a
discriminated stream of :data:`WebexItem` for the connector to transform.

Full-crawl only. Cursor pagination is driven by the RFC5988 ``Link`` header
(exposed by httpx as ``response.links``). ``429`` responses are retried honoring
the ``Retry-After`` header.

Permissions are fail-closed: if a room's memberships cannot be read, the room and
its messages are skipped rather than indexed without access controls.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Iterable, List, Optional

import httpx

from examples.webex.models import (
    MessageItem,
    RoomItem,
    WebexItem,
    WebexMessage,
    WebexRoom,
)
from glean.indexing.connectors import BaseStreamingDataClient

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://webexapis.com/v1"


class WebexDataClient(BaseStreamingDataClient[WebexItem]):
    """Streams Webex rooms and messages from the Webex REST API.

    Args:
        api_token: Webex bearer token.
        base_url: Webex API base URL.
        room_types: Which room types to crawl. Defaults to ``("group",)`` --
            direct (1:1) rooms are excluded by default.
        page_size: ``max`` query-param page size (Webex caps this per endpoint).
        max_retries: Max retries for ``429``/transient errors per request.
        client: Optional pre-built ``httpx.Client`` (tests inject a
            ``MockTransport``). When omitted, a client is built lazily.
    """

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        room_types: Iterable[str] = ("group",),
        page_size: int = 100,
        max_retries: int = 5,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._room_types = set(room_types)
        self._page_size = page_size
        self._max_retries = max_retries
        self._client = client

    # -- HTTP plumbing ----------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_token}"},
                timeout=30.0,
            )
        return self._client

    def _request(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """GET a URL, retrying on 429 (honoring Retry-After) and transient 5xx."""
        client = self._get_client()
        attempt = 0
        while True:
            response = client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self._max_retries:
                    response.raise_for_status()
                retry_after = _retry_after_seconds(response, default=2**attempt)
                logger.warning(
                    "Webex %s on %s (trackingid=%s); retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    url,
                    response.headers.get("trackingid", "?"),
                    retry_after,
                    attempt + 1,
                    self._max_retries,
                )
                time.sleep(retry_after)
                attempt += 1
                continue
            response.raise_for_status()
            return response

    def _paginate(self, path: str, params: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """Yield items across all pages, following the ``Link: rel=next`` cursor."""
        url: Optional[str] = path
        page_params: Optional[Dict[str, Any]] = {**params, "max": self._page_size}
        while url:
            response = self._request(url, params=page_params)
            payload = response.json()
            for item in payload.get("items", []):
                yield item
            next_link = response.links.get("next")
            # The next link is an absolute URL that already encodes the cursor, so
            # subsequent requests must not re-send the original query params.
            url = next_link.get("url") if next_link else None
            page_params = None

    # -- Source reads -----------------------------------------------------

    def _list_rooms(self) -> Generator[WebexRoom, None, None]:
        for room in self._paginate("/rooms", {}):
            if room.get("type") in self._room_types:
                yield room  # type: ignore[misc]

    def _list_member_emails(self, room_id: str) -> List[str]:
        emails: List[str] = []
        for membership in self._paginate("/memberships", {"roomId": room_id}):
            email = membership.get("personEmail")
            if email:
                emails.append(email)
        return emails

    def _list_messages(self, room_id: str) -> Generator[WebexMessage, None, None]:
        for message in self._paginate("/messages", {"roomId": room_id}):
            yield message  # type: ignore[misc]

    # -- Streaming entrypoint --------------------------------------------

    def get_source_data(self, **kwargs: Any) -> Generator[WebexItem, None, None]:
        """Yield rooms and their messages as a discriminated stream.

        ``since`` is accepted for interface compatibility but ignored: v1 is
        full-crawl only (incremental is documented follow-up work).
        """
        if kwargs.get("since"):
            logger.info("Webex connector is full-crawl only; ignoring 'since'=%s", kwargs["since"])

        rooms_scanned = 0
        rooms_skipped = 0
        messages_seen = 0

        for room in self._list_rooms():
            room_id = room.get("id")
            if not room_id:
                continue
            try:
                member_emails = self._list_member_emails(room_id)
            except httpx.HTTPError as exc:
                # Fail closed: no membership => no permissions => do not index.
                rooms_skipped += 1
                logger.warning("Skipping room %s: could not read memberships (%s)", room_id, exc)
                continue

            rooms_scanned += 1
            room_title = room.get("title", "")
            logger.info(
                "Fetching room %s ('%s') with %d members", room_id, room_title, len(member_emails)
            )

            yield RoomItem(kind="room", room=room, member_emails=member_emails)

            for message in self._list_messages(room_id):
                messages_seen += 1
                yield MessageItem(
                    kind="message",
                    message=message,
                    room_title=room_title,
                    member_emails=member_emails,
                )

        logger.info(
            "Webex fetch complete: %d rooms indexed, %d skipped, %d messages",
            rooms_scanned,
            rooms_skipped,
            messages_seen,
        )


def _retry_after_seconds(response: httpx.Response, default: float) -> float:
    """Parse the Retry-After header (integer seconds); fall back to ``default``."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(default)
