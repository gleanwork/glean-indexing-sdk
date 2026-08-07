"""Streaming data client for Webex messages via the compliance Events API.

Full-org message coverage requires the compliance Events endpoint; the ordinary
per-room ``GET /messages?roomId=`` is invisible to rooms the token is not a member of.
See ``.glean/api_inventory.md`` and ``.glean/source_investigation.md``.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Generator, List, Optional

import requests

from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient

from .webex_types import WebexMember, WebexMessage

logger = logging.getLogger(__name__)

# The Events API rejects searches wholly older than 90 days. Stay just inside the
# window so a full crawl covers as much history as Webex allows.
_HISTORY_WINDOW_DAYS = 89
_DEFAULT_PAGE_SIZE = 100
_MAX_RETRIES = 5
_RETRY_STATUSES = frozenset({500, 502, 503, 504})
# Safety cap so a misbehaving cursor cannot loop forever.
_MAX_PAGES = 10_000


class WebexComplianceClient(BaseStreamingDataClient[WebexMessage]):
    """Streams org-wide Webex messages, enriched with space title and members."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://webexapis.com/v1",
        history_window_days: int = _HISTORY_WINDOW_DAYS,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ):
        self.base_url = base_url.rstrip("/")
        self.history_window_days = history_window_days
        self.page_size = page_size
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        # Per-crawl caches keyed by roomId to avoid refetching room metadata/members.
        self._room_title_cache: Dict[str, str] = {}
        self._members_cache: Dict[str, List[WebexMember]] = {}

    def _window(self) -> tuple[str, str]:
        """Return (from, to) ISO timestamps for the rolling compliance window."""
        now = datetime.now(timezone.utc)
        from_ts = (now - timedelta(days=self.history_window_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        to_ts = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return from_ts, to_ts

    def _iter_message_events(self) -> Generator[dict, None, None]:
        """Yield raw ``created`` message-event payloads across all pages."""
        from_ts, to_ts = self._window()
        url: Optional[str] = f"{self.base_url}/events"
        params: Optional[dict] = {
            "resource": "messages",
            "from": from_ts,
            "to": to_ts,
            "max": self.page_size,
        }
        logger.info("Fetching Webex message events from %s to %s", from_ts, to_ts)
        page = 0
        while url:
            payload, next_url = self._get_with_pagination(url, params)
            params = None  # subsequent pages use the fully-formed Link URL
            page += 1
            items = payload.get("items", [])
            logger.info("Events page %d: %d events", page, len(items))
            for event in items:
                if event.get("type") != "created":
                    continue  # V1 indexes newly-created messages only
                data = event.get("data", {})
                if data.get("id") and data.get("roomId"):
                    yield data
            if page >= _MAX_PAGES:
                logger.warning("Reached page cap (%d); stopping pagination", _MAX_PAGES)
                break
            url = next_url

    def get_source_data(self, since: Optional[str] = None, **kwargs) -> Generator[WebexMessage, None, None]:
        """Yield created messages from the last ``history_window_days`` days.

        ``since`` is accepted for interface compatibility but V1 is full-crawl only;
        the crawl window is always the rolling compliance window.
        """
        del kwargs  # accepted for interface compatibility
        if since:
            logger.debug("Ignoring 'since=%s'; V1 is full-crawl only", since)
        for data in self._iter_message_events():
            room_id = data["roomId"]
            members = self._room_members(room_id, data.get("personEmail", ""))
            yield WebexMessage(
                id=data["id"],
                room_id=room_id,
                room_type=data.get("roomType", ""),
                room_title=self._room_title(room_id),
                text=data.get("text", ""),
                person_id=data.get("personId", ""),
                person_email=data.get("personEmail", ""),
                created=data.get("created", ""),
                member_emails=[m["email"] for m in members],
            )

    def collect_users(self) -> List[WebexMember]:
        """Return the unique set of users that appear in any indexed room's ACL.

        Walks the event window once to discover the rooms with activity, then unions
        their memberships. Membership lookups are cached, so a subsequent document
        crawl on the same client instance does not refetch them.
        """
        users: Dict[str, WebexMember] = {}
        for data in self._iter_message_events():
            for member in self._room_members(data["roomId"], data.get("personEmail", "")):
                users.setdefault(member["email"], member)
        logger.info("Collected %d unique ACL users across active rooms", len(users))
        return list(users.values())

    def _room_title(self, room_id: str) -> str:
        """Return a room's title, caching per crawl. Falls back to the room id."""
        if room_id in self._room_title_cache:
            return self._room_title_cache[room_id]
        title = room_id
        try:
            resp = self._request("GET", f"{self.base_url}/rooms/{room_id}")
            if resp.status_code == 200:
                title = resp.json().get("title") or room_id
            else:
                logger.warning("Room %s title fetch returned HTTP %d", room_id, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("Room %s title fetch failed: %s", room_id, exc)
        self._room_title_cache[room_id] = title
        return title

    def _room_members(self, room_id: str, author_email: str) -> List[WebexMember]:
        """Return member records for a room (the document ACL), caching per crawl.

        Falls back to the author so a message is never left world-visible if
        membership cannot be resolved.
        """
        if room_id in self._members_cache:
            return self._members_cache[room_id]
        members: List[WebexMember] = []
        seen: set[str] = set()
        url: Optional[str] = f"{self.base_url}/memberships"
        params: Optional[dict] = {"roomId": room_id, "max": self.page_size}
        try:
            while url:
                resp = self._request("GET", url, params=params)
                params = None
                if resp.status_code != 200:
                    logger.warning("Memberships for room %s returned HTTP %d", room_id, resp.status_code)
                    break
                for m in resp.json().get("items", []):
                    email = m.get("personEmail")
                    if email and email not in seen:
                        seen.add(email)
                        members.append(WebexMember(email=email, name=m.get("personDisplayName") or email))
                url = self._next_link(resp)
        except requests.RequestException as exc:
            logger.warning("Membership fetch failed for room %s: %s", room_id, exc)

        if not members and author_email:
            members = [WebexMember(email=author_email, name=author_email)]
        self._members_cache[room_id] = members
        return members

    def _get_with_pagination(self, url: str, params: Optional[dict]):
        """Perform a GET and return (json_body, next_page_url_or_None)."""
        resp = self._request("GET", url, params=params)
        resp.raise_for_status()
        return resp.json(), self._next_link(resp)

    @staticmethod
    def _next_link(resp: requests.Response) -> Optional[str]:
        """Extract the ``rel="next"`` URL from Webex's Link header, if present."""
        link = resp.headers.get("Link") or resp.headers.get("link")
        if not link:
            return None
        for part in link.split(","):
            segments = part.split(";")
            if len(segments) < 2:
                continue
            if 'rel="next"' in segments[1]:
                return segments[0].strip().strip("<>")
        return None

    def _request(self, method: str, url: str, params: Optional[dict] = None) -> requests.Response:
        """Issue a request, retrying on 429 and transient 5xx with backoff."""
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.request(method, url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_exc = exc
                sleep_s = min(2**attempt, 30)
                logger.warning("Request error (%s); retry in %ds (attempt %d/%d)", exc, sleep_s, attempt + 1, _MAX_RETRIES)
                time.sleep(sleep_s)
                continue
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1") or "1")
                logger.warning("Rate limited (429); sleeping %ds (attempt %d/%d)", retry_after, attempt + 1, _MAX_RETRIES)
                time.sleep(retry_after)
                continue
            if resp.status_code in _RETRY_STATUSES:
                sleep_s = min(2**attempt, 30)
                logger.warning("Server error %d; retry in %ds (attempt %d/%d)", resp.status_code, sleep_s, attempt + 1, _MAX_RETRIES)
                time.sleep(sleep_s)
                continue
            return resp
        if last_exc is not None:
            raise last_exc
        # Exhausted retries on repeated 429/5xx; return the last response so the
        # caller's raise_for_status surfaces a clear error.
        return self._session.request(method, url, params=params, timeout=30)
