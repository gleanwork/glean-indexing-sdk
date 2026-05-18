"""Tests for the Webex connector snippet."""

from unittest.mock import MagicMock, patch

from glean.indexing.models import IndexingMode
from glean.indexing.pull import BearerTokenAuth, PullHttpClient, PullOptions, PullRetryOptions

from snippets.webex.client import WEBEX_TOKEN_URL, WebexClient, WebexOAuthTokenManager
from snippets.webex.checkpoint import FileCheckpointStore
from snippets.webex.connector import WebexConnector
from snippets.webex.data_client import WebexDataClient
from snippets.webex.run_connector import _auth_from_env, _checkpoint_store_from_env


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


def test_webex_connector_writes_file_checkpoint_after_successful_push(httpx_mock, tmp_path):
    httpx_mock.add_response(
        url="https://webexapis.com/v1/people?max=1000",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/teams?max=100",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/rooms?max=100&sortBy=lastactivity",
        json={
            "items": [
                {"id": "room-1", "lastActivity": "2026-05-18T00:10:00Z"},
                {"id": "room-2", "lastActivity": "2026-05-18T00:20:00Z", "isPublic": True},
            ]
        },
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/memberships?roomId=room-1&max=100",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/messages?roomId=room-1&max=50",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/messages?roomId=room-2&max=50",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )
    checkpoint_store = FileCheckpointStore(tmp_path / "webex-checkpoint.json")
    connector = WebexConnector(
        "webex",
        WebexDataClient(WebexClient(_client())),
        checkpoint_store=checkpoint_store,
    )

    with patch("snippets.webex.connector.api_client") as mock_api_client:
        mock_api_client.return_value.__enter__.return_value = MagicMock()
        connector.index_data(mode=IndexingMode.FULL)

    assert checkpoint_store.read_last_activity_cursor() == "2026-05-18T00:20:00Z"


def test_webex_people_falls_back_to_me_for_personal_pat(httpx_mock):
    httpx_mock.add_response(
        url="https://webexapis.com/v1/people?max=1000",
        status_code=400,
        json={"message": "query parameter required"},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://webexapis.com/v1/people/me",
        json={
            "id": "person-me",
            "emails": ["me@example.com"],
            "displayName": "Me",
        },
        headers={"Content-Type": "application/json"},
    )

    people = WebexClient(_client()).list_people()

    assert len(people) == 1
    assert people[0].id == "person-me"
    assert people[0].emails == ["me@example.com"]


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


def test_webex_oauth_token_manager_refreshes_on_demand(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=WEBEX_TOKEN_URL,
        json={"access_token": "access-1", "refresh_token": "refresh-2", "expires_in": 3600},
        headers={"Content-Type": "application/json"},
    )
    token_client = PullHttpClient(
        base_url="https://webexapis.com/v1",
        options=PullOptions(
            retries=PullRetryOptions(initial_backoff_seconds=0, max_backoff_seconds=0)
        ),
    )
    manager = WebexOAuthTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-1",
        token_client=token_client,
    )

    assert manager.headers()["Authorization"] == "Bearer access-1"
    assert manager.refresh_token == "refresh-2"

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert b"grant_type=refresh_token" in request.content
    assert b"refresh_token=refresh-1" in request.content


def test_webex_oauth_token_manager_reuses_unexpired_access_token(httpx_mock):
    token_client = PullHttpClient(base_url="https://webexapis.com/v1")
    manager = WebexOAuthTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-1",
        access_token="access-existing",
        expires_at=9999999999,
        token_client=token_client,
    )

    assert manager.headers()["Authorization"] == "Bearer access-existing"
    assert httpx_mock.get_request() is None


def test_webex_auth_from_env_uses_pat_when_oauth_is_not_configured(monkeypatch):
    monkeypatch.setenv("WEBEX_ACCESS_TOKEN", "pat-token")
    monkeypatch.delenv("WEBEX_CLIENT_ID", raising=False)
    monkeypatch.delenv("WEBEX_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("WEBEX_REFRESH_TOKEN", raising=False)

    auth = _auth_from_env()

    assert auth.headers()["Authorization"] == "Bearer pat-token"


def test_webex_auth_from_env_uses_oauth_when_refresh_config_is_present(monkeypatch):
    monkeypatch.setenv("WEBEX_ACCESS_TOKEN", "initial-token")
    monkeypatch.setenv("WEBEX_CLIENT_ID", "client-id")
    monkeypatch.setenv("WEBEX_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("WEBEX_REFRESH_TOKEN", "refresh-token")

    auth = _auth_from_env()

    assert isinstance(auth, WebexOAuthTokenManager)
    assert auth.access_token == "initial-token"


def test_webex_checkpoint_store_from_env(monkeypatch, tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    monkeypatch.setenv("WEBEX_CHECKPOINT_PATH", str(checkpoint_path))

    store = _checkpoint_store_from_env()

    assert isinstance(store, FileCheckpointStore)
    store.write_last_activity_cursor("2026-05-18T00:00:00Z")
    assert store.read_last_activity_cursor() == "2026-05-18T00:00:00Z"
