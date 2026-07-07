"""Webex source-side data clients.

Two interchangeable data clients, both yielding the same discriminated
:data:`WebexItem` stream so the same :class:`WebexConnector` can consume either:

* :class:`WebexDataClient` -- room-scoped crawl (``GET /rooms`` then
  ``GET /messages`` per room). Sees only rooms the token owner belongs to
  (bot or plain user token).
* :class:`WebexEventsDataClient` -- **org-wide** crawl via the compliance
  Events API (``GET /events?resource=messages``). Requires the Compliance
  Officer role and ``spark-compliance:*`` scopes; sees every space in the org.

Both are full-crawl only. Cursor pagination is driven by the RFC5988 ``Link``
header (exposed by httpx as ``response.links``). ``429`` responses are retried
honoring the ``Retry-After`` header. Permissions are fail-closed: if a room's
memberships cannot be read, the room and its messages are skipped rather than
indexed without access controls.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
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


class _WebexHttp:
    """Shared Webex HTTP plumbing: auth, retries, and cursor pagination."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        page_size: int = 100,
        max_retries: int = 5,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._page_size = page_size
        self._max_retries = max_retries
        self._client = client

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
            # The next link is an absolute URL that already encodes the cursor
            # (and the resolved from/to window), so we must not re-send params.
            url = next_link.get("url") if next_link else None
            page_params = None

    def _list_member_emails(self, room_id: str) -> List[str]:
        emails: List[str] = []
        for membership in self._paginate("/memberships", {"roomId": room_id}):
            email = membership.get("personEmail")
            if email:
                emails.append(email)
        return emails


class WebexDataClient(_WebexHttp, BaseStreamingDataClient[WebexItem]):
    """Room-scoped Webex crawl (rooms the token owner belongs to).

    Args:
        api_token: Webex bearer token (bot or user token).
        base_url: Webex API base URL.
        room_types: Which room types to crawl. Defaults to ``("group",)`` --
            direct (1:1) rooms are excluded by default.
        page_size: ``max`` query-param page size.
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
        super().__init__(
            api_token,
            base_url=base_url,
            page_size=page_size,
            max_retries=max_retries,
            client=client,
        )
        self._room_types = set(room_types)

    def _list_rooms(self) -> Generator[WebexRoom, None, None]:
        for room in self._paginate("/rooms", {}):
            if room.get("type") in self._room_types:
                yield room  # type: ignore[misc]

    def _list_messages(self, room_id: str) -> Generator[WebexMessage, None, None]:
        for message in self._paginate("/messages", {"roomId": room_id}):
            yield message  # type: ignore[misc]

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


class WebexEventsDataClient(_WebexHttp, BaseStreamingDataClient[WebexItem]):
    """Org-wide Webex crawl via the compliance Events API.

    Iterates ``GET /events?resource=messages`` (org-wide for a Compliance
    Officer token), discovering rooms lazily. Each room's title and current
    membership are fetched once and cached; the room is emitted as a Space
    document the first time it is seen, followed by its messages.

    Args:
        api_token: Compliance Officer bearer token.
        base_url: Webex API base URL.
        start_date: ISO-8601 ``from`` timestamp bounding the crawl window. When
            ``None``, Webex applies its default window (~90 days). The Events API
            rejects windows older than ~90 days (HTTP 403), so a ``start_date``
            beyond ``max_lookback_days`` is clamped forward with a warning; older
            history requires Webex eDiscovery (out of scope).
        room_types: Which room types to index (by event ``roomType``). Defaults
            to ``("group",)`` -- direct (1:1) rooms excluded.
        event_types: Which message event types to index. Defaults to
            ``("created",)``; message edits/deletions are follow-up work.
        max_lookback_days: Maximum days before now the Events API will accept as
            ``from``. Webex allows ~90; defaults to 89 for a safety margin.
        page_size: ``max`` query-param page size.
        max_retries: Max retries for ``429``/transient errors per request.
        client: Optional pre-built ``httpx.Client`` (tests inject a transport).
    """

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        start_date: Optional[str] = None,
        room_types: Iterable[str] = ("group",),
        event_types: Iterable[str] = ("created",),
        max_lookback_days: int = 89,
        page_size: int = 100,
        max_retries: int = 5,
        client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            api_token,
            base_url=base_url,
            page_size=page_size,
            max_retries=max_retries,
            client=client,
        )
        self._start_date = start_date
        self._room_types = set(room_types)
        self._event_types = set(event_types)
        self._max_lookback_days = max_lookback_days

    def _effective_from(self) -> Optional[str]:
        """Clamp ``start_date`` to the Events API lookback window (~90 days).

        Returns None to let Webex apply its default window when no start was set.
        """
        if not self._start_date:
            return None
        earliest = datetime.now(timezone.utc) - timedelta(days=self._max_lookback_days)
        start = _parse_iso(self._start_date)
        if start is not None and start < earliest:
            clamped = earliest.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            logger.warning(
                "start_date %s exceeds the Webex Events API ~%dd retention; clamping to %s "
                "(older history requires Webex eDiscovery)",
                self._start_date,
                self._max_lookback_days,
                clamped,
            )
            return clamped
        return self._start_date

    def _get_room(self, room_id: str) -> WebexRoom:
        response = self._request(f"/rooms/{room_id}")
        return response.json()  # type: ignore[no-any-return]

    def get_source_data(self, **kwargs: Any) -> Generator[WebexItem, None, None]:
        """Yield rooms and messages discovered from the org-wide event stream.

        ``since`` is accepted for interface compatibility but ignored: v1 is
        full-crawl only. Deletions/edits are documented follow-up work.
        """
        if kwargs.get("since"):
            logger.info("Webex connector is full-crawl only; ignoring 'since'=%s", kwargs["since"])

        params: Dict[str, Any] = {"resource": "messages"}
        effective_from = self._effective_from()
        if effective_from:
            params["from"] = effective_from
        logger.info(
            "Org-wide Webex crawl via Events API (from=%s, event_types=%s)",
            effective_from or "<api default ~90d>",
            sorted(self._event_types),
        )

        # roomId -> (room, member_emails); value is None for fail-closed skips.
        room_cache: Dict[str, Optional[tuple]] = {}
        rooms_emitted = 0
        rooms_skipped = 0
        messages_seen = 0

        for event in self._paginate("/events", params):
            if event.get("type") not in self._event_types:
                continue
            data = event.get("data", {})
            room_id = data.get("roomId")
            if not data.get("id") or not room_id:
                continue
            if data.get("roomType") not in self._room_types:
                continue

            if room_id not in room_cache:
                try:
                    member_emails = self._list_member_emails(room_id)
                    room = self._get_room(room_id)
                except httpx.HTTPError as exc:
                    room_cache[room_id] = None
                    rooms_skipped += 1
                    logger.warning(
                        "Skipping room %s: could not read room/memberships (%s)", room_id, exc
                    )
                    continue
                room_cache[room_id] = (room, member_emails)
                rooms_emitted += 1
                logger.info(
                    "Discovered room %s ('%s') with %d members",
                    room_id,
                    room.get("title", ""),
                    len(member_emails),
                )
                yield RoomItem(kind="room", room=room, member_emails=member_emails)

            cached = room_cache[room_id]
            if cached is None:
                continue  # fail-closed room; skip its messages too
            room, member_emails = cached
            messages_seen += 1
            yield MessageItem(
                kind="message",
                message=data,  # type: ignore[typeddict-item]
                room_title=room.get("title", ""),
                member_emails=member_emails,
            )

        logger.info(
            "Webex org-wide fetch complete: %d rooms indexed, %d skipped, %d messages",
            rooms_emitted,
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


def _parse_iso(timestamp: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware datetime, or None if invalid."""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
