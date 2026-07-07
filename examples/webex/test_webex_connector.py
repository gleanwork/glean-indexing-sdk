"""Unit tests for the Webex connector.

Uses an injected ``httpx.MockTransport`` so the data client is exercised
end-to-end (pagination, fail-closed permissions, retries) without hitting the
real API, and the SDK's ``run_connector`` to verify the transform/upload path
against a mock Glean client.
"""

from __future__ import annotations

import httpx

from examples.webex.connector import WebexConnector, _message_title, _to_epoch
from examples.webex.data_client import WebexDataClient, WebexEventsDataClient
from glean.indexing.testing import run_connector

ROOMS = {
    "items": [
        {
            "id": "R1",
            "title": "Engineering",
            "type": "group",
            "created": "2026-01-01T00:00:00.000Z",
            "lastActivity": "2026-02-01T00:00:00.000Z",
        },
        {"id": "R2", "title": "DM", "type": "direct", "created": "2026-01-02T00:00:00.000Z"},
        {"id": "R3", "title": "NoAccess", "type": "group", "created": "2026-01-03T00:00:00.000Z"},
    ]
}
MEMBERS = {
    "R1": {
        "items": [
            {"personEmail": "a@acme.com", "personDisplayName": "A"},
            {"personEmail": "b@acme.com", "personDisplayName": "B"},
        ]
    },
}
MESSAGES = {
    "R1": {
        "items": [
            {
                "id": "M1",
                "roomId": "R1",
                "roomType": "group",
                "text": "hello world",
                "personEmail": "a@acme.com",
                "created": "2026-01-10T00:00:00.000Z",
            },
            {
                "id": "M2",
                "roomId": "R1",
                "roomType": "group",
                "text": "second message",
                "personEmail": "b@acme.com",
                "created": "2026-01-11T00:00:00.000Z",
            },
        ]
    },
}


def _handler(request: httpx.Request) -> httpx.Response:
    """Route mock Webex requests to canned fixtures."""
    path = request.url.path
    room_id = request.url.params.get("roomId")
    if path.endswith("/rooms"):
        return httpx.Response(200, json=ROOMS)
    if path.endswith("/memberships"):
        if room_id in MEMBERS:
            return httpx.Response(200, json=MEMBERS[room_id])
        # R3 -> membership read fails (exercises the fail-closed path).
        return httpx.Response(403, json={"message": "forbidden"})
    if path.endswith("/messages"):
        return httpx.Response(200, json=MESSAGES.get(room_id, {"items": []}))
    return httpx.Response(404, json={})


def _client_with_mock() -> WebexDataClient:
    """Build a WebexDataClient backed by the canned mock transport."""
    transport = httpx.MockTransport(_handler)
    http = httpx.Client(
        transport=transport,
        base_url="https://webexapis.com/v1",
        headers={"Authorization": "Bearer test"},
    )
    return WebexDataClient(api_token="test", client=http)


def test_fetch_yields_group_room_and_messages_only() -> None:
    """Group room and its messages are yielded; direct/no-access rooms are not."""
    items = list(_client_with_mock().get_source_data())
    kinds = [i["kind"] for i in items]
    # R1 room + its 2 messages. R2 is direct (excluded), R3 fails membership (skipped).
    assert kinds == ["room", "message", "message"]
    first = items[0]
    assert first["kind"] == "room"
    assert first["room"]["id"] == "R1"
    assert first["member_emails"] == ["a@acme.com", "b@acme.com"]


def test_direct_rooms_excluded_by_default() -> None:
    """Direct (1:1) rooms are not indexed unless explicitly requested."""
    ids = [i["room"]["id"] for i in _client_with_mock().get_source_data() if i["kind"] == "room"]
    assert "R2" not in ids


def test_fail_closed_skips_rooms_without_membership() -> None:
    """A room whose memberships cannot be read is skipped, not indexed openly."""
    ids = [i["room"]["id"] for i in _client_with_mock().get_source_data() if i["kind"] == "room"]
    assert "R3" not in ids


def test_pagination_follows_link_header() -> None:
    """The client follows the RFC5988 Link rel=next cursor across pages."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rooms"):
            if "cursor" not in request.url.params:
                headers = {"Link": '<https://webexapis.com/v1/rooms?cursor=P2>; rel="next"'}
                return httpx.Response(
                    200,
                    headers=headers,
                    json={
                        "items": [
                            {
                                "id": "R1",
                                "title": "P1",
                                "type": "group",
                                "created": "2026-01-01T00:00:00Z",
                            }
                        ]
                    },
                )
            calls["n"] += 1
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "R9",
                            "title": "P2",
                            "type": "group",
                            "created": "2026-01-01T00:00:00Z",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/memberships"):
            return httpx.Response(200, json={"items": [{"personEmail": "x@acme.com"}]})
        return httpx.Response(200, json={"items": []})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://webexapis.com/v1")
    client = WebexDataClient(api_token="t", client=http)
    rooms = [i["room"]["id"] for i in client.get_source_data() if i["kind"] == "room"]
    assert rooms == ["R1", "R9"]  # second page followed via Link header
    assert calls["n"] == 1


def test_retry_on_429_then_success(monkeypatch) -> None:  # noqa: ANN001
    """A 429 is retried (honoring Retry-After) and then succeeds."""
    import examples.webex.data_client as dc

    monkeypatch.setattr(dc.time, "sleep", lambda _s: None)  # do not actually wait
    state = {"hits": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rooms"):
            state["hits"] += 1
            if state["hits"] == 1:
                return httpx.Response(429, headers={"Retry-After": "1"}, json={})
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"items": []})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://webexapis.com/v1")
    client = WebexDataClient(api_token="t", client=http)
    list(client.get_source_data())
    assert state["hits"] == 2  # retried once after 429


def test_run_connector_produces_documents_with_permissions() -> None:
    """The full transform/upload path posts documents scoped to room members."""
    connector = WebexConnector(_client_with_mock())
    result = run_connector(connector)
    docs = result.documents_posted
    assert len(docs) == 3  # 1 space + 2 messages
    assert {d.object_type for d in docs} == {"Space", "Message"}
    for d in docs:
        assert d.permissions is not None and d.permissions.allowed_users is not None
        emails = {u.email for u in d.permissions.allowed_users}
        assert emails == {"a@acme.com", "b@acme.com"}
        assert d.datasource == "webex"
    messages = [d for d in docs if d.object_type == "Message"]
    assert all(d.body is not None and d.body.text_content for d in messages)
    assert all(d.author is not None and d.author.email for d in messages)


def test_timestamp_and_title_helpers() -> None:
    """Timestamp parsing and message-title derivation behave as specified."""
    assert _to_epoch("2026-01-01T00:00:00.000Z") == 1767225600
    assert _to_epoch(None) is None
    assert _to_epoch("not-a-date") is None
    assert _message_title("a@acme.com", "Eng", "hi there") == "a@acme.com in Eng: hi there"
    long_title = _message_title("a@acme.com", "Eng", "x" * 500)
    assert len(long_title) <= 120


# --- Org-wide Events API client -------------------------------------------

EVENTS = {
    "items": [
        {
            "id": "E1",
            "resource": "messages",
            "type": "created",
            "created": "2026-01-10T00:00:00.000Z",
            "data": {
                "id": "M1",
                "roomId": "R1",
                "roomType": "group",
                "text": "org-wide hello",
                "personEmail": "a@acme.com",
                "created": "2026-01-10T00:00:00.000Z",
            },
        },
        {
            "id": "E2",
            "resource": "messages",
            "type": "created",
            "created": "2026-01-11T00:00:00.000Z",
            "data": {
                "id": "M2",
                "roomId": "R1",
                "roomType": "group",
                "text": "second org message",
                "personEmail": "b@acme.com",
                "created": "2026-01-11T00:00:00.000Z",
            },
        },
        {
            "id": "E3",
            "resource": "messages",
            "type": "deleted",  # should be skipped by default event_types
            "created": "2026-01-12T00:00:00.000Z",
            "data": {"id": "M9", "roomId": "R1", "roomType": "group"},
        },
        {
            "id": "E4",
            "resource": "messages",
            "type": "created",
            "created": "2026-01-13T00:00:00.000Z",
            "data": {
                "id": "M3",
                "roomId": "RD",
                "roomType": "direct",  # DM, excluded by default
                "text": "dm message",
                "personEmail": "c@acme.com",
                "created": "2026-01-13T00:00:00.000Z",
            },
        },
    ]
}
ROOM_R1 = {"id": "R1", "title": "Org Space", "type": "group", "created": "2026-01-01T00:00:00Z"}


def _events_handler(request: httpx.Request) -> httpx.Response:
    """Route mock org-wide Events/room/membership requests."""
    path = request.url.path
    if path.endswith("/events"):
        return httpx.Response(200, json=EVENTS)
    if path.endswith("/memberships"):
        return httpx.Response(
            200, json={"items": [{"personEmail": "a@acme.com"}, {"personEmail": "b@acme.com"}]}
        )
    if "/rooms/" in path:
        return httpx.Response(200, json=ROOM_R1)
    return httpx.Response(404, json={})


def _events_client() -> WebexEventsDataClient:
    """Build a WebexEventsDataClient backed by the canned mock transport."""
    http = httpx.Client(
        transport=httpx.MockTransport(_events_handler), base_url="https://webexapis.com/v1"
    )
    return WebexEventsDataClient(api_token="t", client=http)


def test_events_client_streams_room_then_messages() -> None:
    """Org-wide client emits a room once, then its group messages; DMs/deletes excluded."""
    items = list(_events_client().get_source_data())
    kinds = [i["kind"] for i in items]
    # R1 room (emitted once) + M1 + M2. M9 is a delete, M3 is a DM -> both excluded.
    assert kinds == ["room", "message", "message"]
    first = items[0]
    assert first["kind"] == "room"
    assert first["room"]["id"] == "R1"
    assert first["member_emails"] == ["a@acme.com", "b@acme.com"]
    message_ids = [i["message"]["id"] for i in items if i["kind"] == "message"]
    assert message_ids == ["M1", "M2"]


def test_events_client_room_emitted_only_once() -> None:
    """A room shared by multiple messages is emitted a single time."""
    rooms = [i for i in _events_client().get_source_data() if i["kind"] == "room"]
    assert len(rooms) == 1


def test_events_client_full_transform_permissions() -> None:
    """Org-wide path produces permissioned documents through the connector."""
    result = run_connector(WebexConnector(_events_client()))
    docs = result.documents_posted
    assert len(docs) == 3  # 1 space + 2 messages
    assert {d.object_type for d in docs} == {"Space", "Message"}
    for d in docs:
        assert d.permissions is not None and d.permissions.allowed_users is not None
        assert {u.email for u in d.permissions.allowed_users} == {"a@acme.com", "b@acme.com"}


def test_events_client_clamps_start_date_beyond_lookback() -> None:
    """A start_date older than the lookback window is clamped, not sent as-is."""
    captured = {"from": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            captured["from"] = request.url.params.get("from")
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"items": []})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://webexapis.com/v1")
    client = WebexEventsDataClient(
        api_token="t", start_date="2000-01-01T00:00:00.000Z", max_lookback_days=89, client=http
    )
    list(client.get_source_data())
    # The ancient start date must have been clamped forward to a recent value.
    assert captured["from"] is not None
    assert not captured["from"].startswith("2000")
