"""Webex source client built on the SDK pull layer."""

from collections.abc import Iterable, Mapping

from glean.indexing.pull import LinkHeaderPaginator, PullHttpClient

from snippets.webex.models import WebexMembership, WebexMessage, WebexPerson, WebexRoom, WebexTeam

WEBEX_API_BASE_URL = "https://webexapis.com/v1"


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
