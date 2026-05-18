"""Webex source client built on the SDK pull layer."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from time import time

from glean.indexing.pull import LinkHeaderPaginator, PullHttpClient
from glean.indexing.pull.options import AuthProvider

from snippets.webex.models import WebexMembership, WebexMessage, WebexPerson, WebexRoom, WebexTeam

WEBEX_API_BASE_URL = "https://webexapis.com/v1"
WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"


@dataclass
class WebexOAuthTokenManager(AuthProvider):
    """On-demand OAuth token refresh for Webex.

    This intentionally refreshes only when request headers are needed and the
    current access token is missing or expired. It avoids background scheduling
    while still supporting long-running connector processes.
    """

    client_id: str
    client_secret: str
    refresh_token: str
    token_client: PullHttpClient
    access_token: str | None = None
    expires_at: float = 0
    expiry_buffer_seconds: int = 300

    def headers(self) -> Mapping[str, str]:
        """Return a valid authorization header, refreshing on demand."""
        if not self.access_token or time() >= self.expires_at:
            self.refresh()
        return {"Authorization": f"Bearer {self.access_token}"}

    def refresh(self) -> str:
        """Exchange the refresh token for a new access token."""
        response = self.token_client.post(
            WEBEX_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = response.json_dict()
        self.access_token = str(payload["access_token"])
        expires_in = int(payload.get("expires_in", 43200))
        self.expires_at = time() + max(0, expires_in - self.expiry_buffer_seconds)
        rotated_refresh_token = payload.get("refresh_token")
        if rotated_refresh_token:
            self.refresh_token = str(rotated_refresh_token)
        return self.access_token


class WebexClient:
    """Small Webex API wrapper for connector-specific endpoint semantics."""

    def __init__(self, http_client: PullHttpClient):
        """Initialize the client with a generic pull-layer HTTP client."""
        self.http_client = http_client
        self.paginator = LinkHeaderPaginator(http_client)

    def list_people(self) -> list[WebexPerson]:
        """Fetch people visible to the token."""
        return [WebexPerson.from_api(item) for item in self._items("/people", {"max": 1000})]

    def list_teams(self) -> list[WebexTeam]:
        """Fetch teams visible to the token."""
        return [WebexTeam.from_api(item) for item in self._items("/teams", {"max": 100})]

    def list_team_memberships(self, team_id: str) -> list[WebexMembership]:
        """Fetch memberships for a team."""
        return [
            WebexMembership.from_api(item)
            for item in self._items("/team/memberships", {"teamId": team_id, "max": 100})
        ]

    def list_rooms(self, *, since: str | None = None) -> list[WebexRoom]:
        """Fetch rooms, stopping at `lastActivity <= since` for incremental crawls."""
        rooms: list[WebexRoom] = []
        for item in self._items("/rooms", {"max": 100, "sortBy": "lastactivity"}):
            room = WebexRoom.from_api(item)
            if since and room.last_activity and room.last_activity <= since:
                break
            rooms.append(room)
        return rooms

    def list_room_memberships(self, room_id: str) -> list[WebexMembership]:
        """Fetch memberships for a room."""
        return [
            WebexMembership.from_api(item)
            for item in self._items("/memberships", {"roomId": room_id, "max": 100})
        ]

    def list_messages(self, room_id: str) -> list[WebexMessage]:
        """Fetch messages for a room."""
        return [
            WebexMessage.from_api(item)
            for item in self._items("/messages", {"roomId": room_id, "max": 50})
        ]

    def _items(self, path: str, params: Mapping[str, object]) -> Iterable[dict]:
        for item in self.paginator.items(path, params=params):
            if isinstance(item, dict):
                yield item
