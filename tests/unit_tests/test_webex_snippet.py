"""Tests for the Webex connector snippet."""

from unittest.mock import MagicMock, patch

from glean.indexing.models import IndexingMode
from glean.indexing.pull import BearerTokenAuth, PullHttpClient, PullOptions, PullRetryOptions

from snippets.webex.client import WebexClient
from snippets.webex.connector import WebexConnector
from snippets.webex.data_client import WebexDataClient


def _client() -> PullHttpClient:
    return PullHttpClient(
        base_url="https://webexapis.com/v1",
        auth=BearerTokenAuth("webex-token"),
        options=PullOptions(
            retries=PullRetryOptions(
                initial_backoff_seconds=0,
                max_backoff_seconds=0,
            )
        ),
    )


def test_webex_connector_pulls_source_data_and_pushes_identities_and_documents(httpx_mock):
    httpx_mock.add_response(
        url="https://webexapis.com/v1/people?max=1000",
        json={
            "items": [{"id": "person-1", "emails": ["a@example.com"], "displayName": "A Person"}]
        },
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/teams?max=100",
        json={"items": [{"id": "team-1", "name": "Team 1"}]},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/team/memberships?teamId=team-1&max=100",
        json={"items": [{"id": "team-membership-1", "teamId": "team-1", "personId": "person-1"}]},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/rooms?max=100&sortBy=lastactivity",
        json={
            "items": [
                {
                    "id": "room-private",
                    "title": "Private Room",
                    "lastActivity": "2026-05-18T00:00:00Z",
                },
                {
                    "id": "room-public",
                    "title": "Public Room",
                    "isPublic": True,
                    "lastActivity": "2026-05-18T00:00:00Z",
                },
            ]
        },
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/memberships?roomId=room-private&max=100",
        json={
            "items": [{"id": "room-membership-1", "roomId": "room-private", "personId": "person-1"}]
        },
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/messages?roomId=room-private&max=50",
        json={
            "items": [
                {
                    "id": "message-root",
                    "roomId": "room-private",
                    "text": "hello",
                    "personId": "person-1",
                    "created": "2026-05-18T00:01:00Z",
                },
                {
                    "id": "message-reply",
                    "roomId": "room-private",
                    "text": "reply",
                    "personId": "person-1",
                    "parentId": "message-root",
                    "created": "2026-05-18T00:02:00Z",
                },
            ]
        },
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/messages?roomId=room-public&max=50",
        json={"items": [{"id": "public-message", "roomId": "room-public", "text": "public"}]},
        headers={"Content-Type": "application/json"},
    )

    connector = WebexConnector("webex", WebexDataClient(WebexClient(_client())))
    mock_glean = MagicMock()

    with patch("snippets.webex.connector.api_client") as mock_api_client:
        mock_api_client.return_value.__enter__.return_value = mock_glean
        connector.index_data(mode=IndexingMode.FULL)

    assert mock_glean.indexing.permissions.bulk_index_users.call_count == 1
    assert mock_glean.indexing.permissions.bulk_index_groups.call_count == 1
    membership_calls = mock_glean.indexing.permissions.bulk_index_memberships.call_args_list
    assert {call.kwargs["group"] for call in membership_calls} == {"team-1", "room-private"}

    docs = mock_glean.indexing.documents.bulk_index.call_args.kwargs["documents"]
    assert [doc.id for doc in docs] == [
        "room-private",
        "room-public",
        "message-root",
        "public-message",
    ]
    message_doc = next(doc for doc in docs if doc.id == "message-root")
    assert message_doc.body and "reply" in message_doc.body.text_content


def test_webex_incremental_room_fetch_stops_at_last_activity_cursor(httpx_mock, monkeypatch):
    monkeypatch.setenv("WEBEX_LAST_ACTIVITY_CURSOR", "2026-05-18T00:00:00Z")
    httpx_mock.add_response(
        url="https://webexapis.com/v1/rooms?max=100&sortBy=lastactivity",
        json={
            "items": [
                {"id": "new-room", "lastActivity": "2026-05-18T00:10:00Z"},
                {"id": "old-room", "lastActivity": "2026-05-18T00:00:00Z"},
                {"id": "older-room", "lastActivity": "2026-05-17T00:00:00Z"},
            ]
        },
        headers={"Content-Type": "application/json"},
    )

    rooms = WebexClient(_client()).list_rooms(since="2026-05-18T00:00:00Z")

    assert [room.id for room in rooms] == ["new-room"]
