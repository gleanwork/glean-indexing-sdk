"""Source-side pull logic for the Webex connector.

Org-wide crawl driven by the Webex **compliance Events API**:

1. Page ``/events?resource=messages&type=deleted`` -> set of deleted message ids.
2. Page ``type=created`` then ``type=updated`` -> latest message ``data`` per id
   (updated supersedes created), grouped by room, minus deleted ids.
3. Per unique room: ``GET /rooms/{id}`` (details) + ``GET /memberships?roomId=``
   (member emails for the ACL).
4. Yield one ``SpaceRecord`` per room followed by its ``MessageRecord`` s.

The Events feed only reaches back ~90 days (hard Webex platform cap), so this is
a rolling-window full crawl. See ``.glean/connector_plan.md`` for the full design.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional

import httpx

from glean.indexing.connectors import BaseStreamingDataClient

from models import MessageRecord, SpaceRecord, WebexRecord, WebexRoom

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://webexapis.com/v1"
DEFAULT_PAGE_SIZE = 100
DEFAULT_LOOKBACK_DAYS = 89  # kept safely under the ~90-day Events API cap
MAX_RETRIES = 5
REQUEST_TIMEOUT_S = 30.0


class WebexDataClient(BaseStreamingDataClient[WebexRecord]):
    """Streaming data client that pulls org-wide Webex content via the Events API."""

    def __init__(
        self,
        access_token: str,
        base_url: str = DEFAULT_BASE_URL,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        page_size: int = DEFAULT_PAGE_SIZE,
        now: Optional[datetime] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        if not access_token:
            raise ValueError("A Webex access token (compliance officer) is required")
        self._token = access_token
        self._base_url = base_url.rstrip("/")
        self._lookback_days = lookback_days
        self._page_size = page_size
        self._now = now
        # Optional injected transport (used in tests via httpx.MockTransport).
        self._transport = transport
        # Distinct room members seen during the crawl: email -> display name.
        # Used to push datasource users before documents (ACLs reference them).
        self.members: Dict[str, str] = {}
        # Lightweight runtime metrics surfaced to the caller for observability.
        self.counters: Dict[str, int] = {
            "events_fetched": 0,
            "messages_fetched": 0,
            "rooms_fetched": 0,
            "rooms_skipped": 0,
            "memberships_fetched": 0,
            "deleted_skipped": 0,
            "webex_api_429_retries": 0,
        }

    # -- HTTP helpers -------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(
        self,
        client: httpx.Client,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """GET with retry/backoff on 429 and 5xx. Never logs the bearer token."""
        last: Optional[httpx.Response] = None
        for attempt in range(MAX_RETRIES):
            resp = client.get(url, params=params, headers=self._headers())
            last = resp
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5") or "5")
                self.counters["webex_api_429_retries"] += 1
                logger.warning(
                    "Webex 429 rate limited on %s; backing off %ss (attempt %d/%d)",
                    _redact(url),
                    retry_after,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                backoff = 2**attempt
                logger.warning(
                    "Webex %d on %s; retrying in %ss (attempt %d/%d)",
                    resp.status_code,
                    _redact(url),
                    backoff,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp
        assert last is not None
        last.raise_for_status()
        return last

    def _paginate(
        self,
        client: httpx.Client,
        path: str,
        params: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield ``items`` across pages, following the ``Link: rel=next`` cursor."""
        next_url: Optional[str] = f"{self._base_url}{path}"
        next_params: Optional[Dict[str, Any]] = dict(params)
        while next_url:
            resp = self._get(client, next_url, params=next_params)
            body = resp.json()
            for item in body.get("items", []):
                yield item
            link = resp.links.get("next")
            if link and link.get("url"):
                next_url = link["url"]  # cursor + window already encoded in the URL
                next_params = None
            else:
                next_url = None

    # -- Window -------------------------------------------------------------

    def _events_window(self) -> tuple[str, str]:
        now = self._now or datetime.now(timezone.utc)
        frm = now - timedelta(days=self._lookback_days)
        return _iso(frm), _iso(now)

    # -- Main crawl ---------------------------------------------------------

    def get_source_data(
        self, since: Optional[str] = None, **_kwargs: Any
    ) -> Generator[WebexRecord, None, None]:
        """Stream Space then Message records for the org-wide 90-day window.

        ``since`` is accepted because the base connector forwards it, but v1 is a
        rolling-window full crawl and ignores it. Incremental use of ``since`` is
        documented as follow-up work in ``.glean/connector_plan.md``.
        """
        if since:
            logger.info("Ignoring since=%s: Webex v1 connector is full-crawl only", since)
        del _kwargs  # base connector may forward extra kwargs; unused in v1
        frm, to = self._events_window()
        base_params = {"resource": "messages", "from": frm, "to": to, "max": self._page_size}

        client_kwargs: dict[str, Any] = {"timeout": REQUEST_TIMEOUT_S}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        with httpx.Client(**client_kwargs) as client:
            me = self._get(client, f"{self._base_url}/people/me").json()
            logger.info(
                "Webex auth OK as %s (org present=%s); crawling events %s..%s",
                me.get("displayName", "?"),
                bool(me.get("orgId")),
                frm,
                to,
            )

            # 1. deleted ids in the window
            deleted_ids = set()
            for ev in self._paginate(client, "/events", {**base_params, "type": "deleted"}):
                data = ev.get("data") or {}
                if data.get("id"):
                    deleted_ids.add(data["id"])
            logger.info("Webex: %d deleted message id(s) in window", len(deleted_ids))

            # 2. created then updated -> latest data per id (updated wins)
            messages_by_id: Dict[str, Dict[str, Any]] = {}
            for etype in ("created", "updated"):
                for ev in self._paginate(client, "/events", {**base_params, "type": etype}):
                    self.counters["events_fetched"] += 1
                    data = ev.get("data") or {}
                    mid = data.get("id")
                    if mid:
                        messages_by_id[mid] = data

            for mid in deleted_ids:
                if messages_by_id.pop(mid, None) is not None:
                    self.counters["deleted_skipped"] += 1

            # 3. group surviving messages by room
            rooms_msgs: Dict[str, List[Dict[str, Any]]] = {}
            for data in messages_by_id.values():
                rid = data.get("roomId")
                if rid:
                    rooms_msgs.setdefault(rid, []).append(data)
            self.counters["messages_fetched"] = sum(len(v) for v in rooms_msgs.values())
            logger.info(
                "Webex: %d message(s) across %d room(s) after edit/delete reconciliation",
                self.counters["messages_fetched"],
                len(rooms_msgs),
            )

            # 4. per room: details + ACL, then yield space + its messages
            for rid, msgs in rooms_msgs.items():
                try:
                    room = self._get_room(client, rid)
                    member_emails = self._get_member_emails(client, rid)
                except httpx.HTTPStatusError as exc:
                    self.counters["rooms_skipped"] += 1
                    logger.warning(
                        "Skipping room %s: could not fetch details/membership (%s)",
                        _short_id(rid),
                        exc.response.status_code,
                    )
                    continue

                self.counters["rooms_fetched"] += 1
                room_title = room.get("title") or "(untitled space)"
                yield SpaceRecord(kind="space", room=room, member_emails=member_emails)
                for data in sorted(msgs, key=lambda m: m.get("created", "")):
                    yield MessageRecord(
                        kind="message",
                        message=data,  # type: ignore[typeddict-item]
                        room_title=room_title,
                        member_emails=member_emails,
                    )

    def _get_room(self, client: httpx.Client, room_id: str) -> WebexRoom:
        return self._get(client, f"{self._base_url}/rooms/{room_id}").json()

    def _get_member_emails(self, client: httpx.Client, room_id: str) -> List[str]:
        emails: List[str] = []
        for m in self._paginate(
            client, "/memberships", {"roomId": room_id, "max": self._page_size}
        ):
            self.counters["memberships_fetched"] += 1
            email = m.get("personEmail")
            if email:
                emails.append(email)
                # Track the member so the connector can push them as a
                # datasource user before referencing them in a document ACL.
                self.members.setdefault(email, m.get("personDisplayName") or email)
        return emails


def _iso(dt: datetime) -> str:
    """Format a datetime as the millisecond-precision UTC ISO8601 Webex expects."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _redact(url: str) -> str:
    """Strip any cursor value from a URL before logging."""
    if "cursor=" not in url:
        return url
    head, _, tail = url.partition("cursor=")
    rest = tail.split("&", 1)
    suffix = ("&" + rest[1]) if len(rest) > 1 else ""
    return f"{head}cursor=<REDACTED>{suffix}"


def _short_id(value: str) -> str:
    return value[:12] + "..." if len(value) > 12 else value
