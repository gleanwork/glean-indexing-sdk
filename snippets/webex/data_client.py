"""Webex data client that composes Webex-specific fetches."""

from typing import Optional, Sequence

from glean.indexing.connectors import BaseDataClient

from snippets.webex.client import WebexClient
from snippets.webex.models import WebexCrawlData


class WebexDataClient(BaseDataClient[WebexCrawlData]):
    """Fetches a full Webex crawl graph using the generic pull layer."""

    def __init__(self, webex_client: WebexClient):
        """Initialize the data client."""
        self.webex_client = webex_client
        self._cache: dict[Optional[str], WebexCrawlData] = {}

    def get_source_data(self, since: Optional[str] = None) -> Sequence[WebexCrawlData]:
        """Fetch Webex people, teams, rooms, memberships, and messages."""
        return [self.fetch(since=since)]

    def fetch(self, since: Optional[str] = None) -> WebexCrawlData:
        """Fetch Webex data and cache it for identity + document phases."""
        if since in self._cache:
            return self._cache[since]

        people = self.webex_client.list_people()
        teams = self.webex_client.list_teams()
        team_memberships = {
            team.id: self.webex_client.list_team_memberships(team.id) for team in teams if team.id
        }
        rooms = self.webex_client.list_rooms(since=since)
        room_memberships = {
            room.id: [] if room.is_public else self.webex_client.list_room_memberships(room.id)
            for room in rooms
            if room.id
        }
        messages_by_room = {
            room.id: self.webex_client.list_messages(room.id) for room in rooms if room.id
        }

        crawl = WebexCrawlData(
            people=people,
            teams=teams,
            team_memberships=team_memberships,
            rooms=rooms,
            room_memberships=room_memberships,
            messages_by_room=messages_by_room,
        )
        self._cache[since] = crawl
        return crawl
