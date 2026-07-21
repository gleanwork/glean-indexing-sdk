"""Webex compliance data client.

Sources org-wide message content from the Webex **compliance Events API** and
per-room ACLs from the Memberships API. Built on the SDK `PullHttpClient` recipe,
which provides retries, 429 `Retry-After` handling, and redacted request logging.

Coverage model (see .glean/connector_plan.md):
  * Message content: `GET /events?resource=messages` over a rolling window
    (Webex hard-limits the window to the past 90 days).
  * ACL: `GET /memberships?roomId=` (readable org-wide for a compliance officer).
  * Room titles (best-effort): `GET /rooms` (account-visible only).

The client reconciles the message event stream into current state:
created/updated events set the latest message; deleted events remove it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Generator, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.observability import ConnectorObservability
from glean.indexing.recipes.pull import PullHttpClient, PullOptions, PullResponse

from .models import WebexMembership, WebexMessage

logger = logging.getLogger(__name__)

WEBEX_BASE_URL = "https://webexapis.com/v1"
# Webex compliance events can only be searched within the past 90 days.
# Stay safely under the boundary to absorb clock skew / request latency.
MAX_LOOKBACK_DAYS = 90
DEFAULT_LOOKBACK_DAYS = 89
# Webex list endpoints use `max` as the page-size parameter.
DEFAULT_PAGE_SIZE = 100

_LINK_NEXT_RE = re.compile(r"<([^>]+)>\s*;\s*rel=\"?next\"?", re.IGNORECASE)


class WebexComplianceDataClient(BaseDataClient[WebexMessage]):
    """Fetches Webex messages (via compliance events) and room memberships."""

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = WEBEX_BASE_URL,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        page_size: int = DEFAULT_PAGE_SIZE,
        observability: Optional[ConnectorObservability] = None,
        options: Optional[PullOptions] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        """Initialize the Webex compliance data client.

        Args:
            access_token: Webex bearer token (Compliance Officer for org-wide reads).
            base_url: Webex API base URL.
            lookback_days: Coverage window in days (capped at the Webex 90-day limit).
            page_size: Page size sent as the Webex `max` parameter.
            observability: Optional observability instance for request metrics.
            options: Optional pull HTTP options (timeouts, retries).
            http_client: Optional preconfigured `httpx.Client` (custom TLS/CA/proxy).
        """
        if not access_token:
            raise ValueError("access_token is required")
        self.lookback_days = min(lookback_days, MAX_LOOKBACK_DAYS)
        self.page_size = page_size
        self.observability = observability
        self.http = PullHttpClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {access_token}"},
            options=options or PullOptions(),
            observability=observability,
            client=http_client,
        )

    # -- auth / smoke test ------------------------------------------------

    def verify_auth(self) -> dict[str, Any]:
        """Call `/people/me` as an auth smoke test; returns caller identity."""
        return self.http.get("/people/me").json_dict()

    # -- messages (org-wide via compliance events) ------------------------

    def get_source_data(self, **_kwargs: Any) -> list[WebexMessage]:
        """Return the reconciled set of live messages within the coverage window.

        Reconciliation is a single chronological pass over message events:
        created/updated set the latest message body; deleted removes it.
        Messages with empty text are dropped.
        """
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=self.lookback_days)
        params = {
            "resource": "messages",
            "from": _iso(from_dt),
            "to": _iso(to_dt),
            "max": self.page_size,
        }

        messages: dict[str, WebexMessage] = {}
        created = updated = deleted = 0
        for event in self._paginate("/events", params):
            data = event.get("data") or {}
            message_id = data.get("id")
            if not message_id:
                continue
            event_type = event.get("type")
            if event_type in ("created", "updated"):
                messages[message_id] = _message_from_event(data)
                created += event_type == "created"
                updated += event_type == "updated"
            elif event_type == "deleted":
                messages.pop(message_id, None)
                deleted += 1

        live = [m for m in messages.values() if (m.get("text") or "").strip()]
        logger.info(
            "Webex message events reconciled: created=%s updated=%s deleted=%s live=%s window_days=%s",
            created,
            updated,
            deleted,
            len(live),
            self.lookback_days,
        )
        if self.observability:
            self.observability.record_metric("webex_events_created", created)
            self.observability.record_metric("webex_events_updated", updated)
            self.observability.record_metric("webex_events_deleted", deleted)
            self.observability.record_metric("webex_messages_live", len(live))
        return live

    # -- memberships (per-room ACL) --------------------------------------

    def fetch_memberships(self, room_id: str) -> list[WebexMembership]:
        """Fetch all memberships for a room (the room's ACL)."""
        members: list[WebexMembership] = []
        for item in self._paginate("/memberships", {"roomId": room_id, "max": self.page_size}):
            members.append(
                WebexMembership(
                    id=item.get("id", ""),
                    roomId=item.get("roomId", room_id),
                    personId=item.get("personId", ""),
                    personEmail=item.get("personEmail", ""),
                    personDisplayName=item.get("personDisplayName", ""),
                    isModerator=bool(item.get("isModerator", False)),
                )
            )
        return members

    # -- room titles (best-effort, account-visible) ----------------------

    def fetch_room_titles(self) -> dict[str, str]:
        """Return roomId -> title for rooms the account can see (best-effort).

        Compliance events cover all org rooms, but titles are only available for
        rooms the connector account is a member of. Unknown rooms fall back to a
        generic title at transform time.
        """
        titles: dict[str, str] = {}
        try:
            for item in self._paginate("/rooms", {"max": self.page_size}):
                room_id = item.get("id")
                if room_id:
                    titles[room_id] = item.get("title") or ""
        except Exception:  # noqa: BLE001 - titles are optional enrichment
            logger.warning("Could not fetch room titles; continuing without them", exc_info=True)
        return titles

    # -- pagination ------------------------------------------------------

    def _paginate(
        self, path: str, params: Mapping[str, Any]
    ) -> Generator[dict[str, Any], None, None]:
        """Yield `items` across pages, following RFC5988 `Link: rel=next`."""
        next_url: Optional[str] = None
        first = True
        while True:
            response = self.http.get(next_url or path, params=params if first else None)
            body = response.json_dict()
            for item in body.get("items", []) or []:
                yield item
            next_url = _next_link(response)
            first = False
            if not next_url:
                return

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.http.close()


def _iso(dt: datetime) -> str:
    """Format a datetime as Webex-compatible ISO-8601 with milliseconds and Z."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _next_link(response: PullResponse) -> Optional[str]:
    """Extract the `next` URL from a Link header, if present."""
    link = response.headers.get("link") or response.headers.get("Link")
    if not link:
        return None
    match = _LINK_NEXT_RE.search(link)
    return match.group(1) if match else None


def _message_from_event(data: Mapping[str, Any]) -> WebexMessage:
    """Build a WebexMessage from a message event's `data` payload."""
    return WebexMessage(
        id=data.get("id", ""),
        roomId=data.get("roomId", ""),
        roomType=data.get("roomType", ""),
        text=data.get("text", ""),
        personId=data.get("personId", ""),
        personEmail=data.get("personEmail", ""),
        created=data.get("created", ""),
    )
