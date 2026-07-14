from __future__ import annotations

import base64
from collections.abc import Generator, Sequence
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from connectors.zulip.connector import (
    ZulipConnector,
    ZulipCrawlContext,
    ZulipCrawlError,
    ZulipIdentityClient,
    ZulipMessageDataClient,
    ZulipMessageRecord,
    ZulipStream,
    ZulipUser,
    create_zulip_http_client,
)
from glean.indexing.connectors import BaseStreamingDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing import run_connector


class StubPullClient:
    def __init__(self, responses: Sequence[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> SimpleNamespace:
        self.calls.append((path, params))
        return SimpleNamespace(data=next(self.responses))


class StaticMessageClient(BaseStreamingDataClient[ZulipMessageRecord]):
    def __init__(self, records: Sequence[ZulipMessageRecord]) -> None:
        self.records = records
        self.streams: tuple[ZulipStream, ...] = ()

    def set_streams(self, streams: Sequence[ZulipStream]) -> None:
        self.streams = tuple(streams)

    def get_source_data(self, **kwargs: Any) -> Generator[ZulipMessageRecord, None, None]:
        yield from self.records


class StaticIdentityClient:
    def __init__(self, context: ZulipCrawlContext) -> None:
        self.context = context

    def fetch_context(self) -> ZulipCrawlContext:
        return self.context


PUBLIC_STREAM = ZulipStream(
    stream_id=10, name="engineering", invite_only=False, is_web_public=False
)
PRIVATE_STREAM = ZulipStream(stream_id=20, name="leadership", invite_only=True, is_web_public=False)
USER = ZulipUser(
    user_id=7,
    email="user@example.test",
    delivery_email="user@example.com",
    full_name="Example User",
    is_active=True,
    is_bot=False,
)


def _message(
    message_id: int, stream: ZulipStream, *, sender_id: int = USER.user_id
) -> ZulipMessageRecord:
    return ZulipMessageRecord(
        stream=stream,
        message={
            "id": message_id,
            "stream_id": stream.stream_id,
            "sender_id": sender_id,
            "sender_full_name": USER.full_name,
            "subject": "search",
            "content": f"<p>Message {message_id}</p>",
            "timestamp": 1_700_000_000 + message_id,
        },
    )


def _context(*, private: bool = False) -> ZulipCrawlContext:
    streams = {PUBLIC_STREAM.stream_id: PUBLIC_STREAM}
    private_members: dict[int, tuple[int, ...]] = {}
    if private:
        streams[PRIVATE_STREAM.stream_id] = PRIVATE_STREAM
        private_members[PRIVATE_STREAM.stream_id] = (USER.user_id,)
    return ZulipCrawlContext(
        streams=streams,
        users={USER.user_id: USER},
        private_members=private_members,
    )


def _connector(records: Sequence[ZulipMessageRecord], context: ZulipCrawlContext) -> ZulipConnector:
    message_client = StaticMessageClient(records)
    return ZulipConnector(
        "https://example.zulipchat.com",
        message_client,  # type: ignore[arg-type]
        StaticIdentityClient(context),  # type: ignore[arg-type]
    )


def test_create_http_client_uses_basic_auth_without_query_credentials() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"result": "success", "members": []})

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = create_zulip_http_client(
        "https://example.zulipchat.com/",
        "bot@example.com",
        "secret-key",
        client=raw_client,
    )

    client.get("users")

    assert captured_request is not None
    expected = base64.b64encode(b"bot@example.com:secret-key").decode()
    assert captured_request.url == "https://example.zulipchat.com/api/v1/users"
    assert captured_request.headers["Authorization"] == f"Basic {expected}"
    assert "secret-key" not in str(captured_request.url)


def test_message_client_paginates_with_non_overlapping_anchors() -> None:
    pull_client = StubPullClient(
        [
            {
                "result": "success",
                "messages": [
                    {
                        "id": 1,
                        "stream_id": PUBLIC_STREAM.stream_id,
                    },
                    {
                        "id": 2,
                        "stream_id": PUBLIC_STREAM.stream_id,
                    },
                ],
                "found_newest": False,
            },
            {
                "result": "success",
                "messages": [
                    {
                        "id": 3,
                        "stream_id": PUBLIC_STREAM.stream_id,
                    }
                ],
                "found_newest": True,
            },
        ]
    )
    client = ZulipMessageDataClient(pull_client, page_size=2)  # type: ignore[arg-type]
    client.set_streams([PUBLIC_STREAM])

    records = list(client.get_source_data())

    assert [record.message["id"] for record in records] == [1, 2, 3]
    first_params = pull_client.calls[0][1]
    second_params = pull_client.calls[1][1]
    assert first_params is not None
    assert second_params is not None
    assert first_params["anchor"] == "oldest"
    assert first_params["include_anchor"] == "true"
    assert second_params["anchor"] == 2
    assert second_params["include_anchor"] == "false"


def test_message_client_rejects_limited_history() -> None:
    pull_client = StubPullClient(
        [
            {
                "result": "success",
                "messages": [],
                "found_newest": True,
                "history_limited": True,
            }
        ]
    )
    client = ZulipMessageDataClient(pull_client)  # type: ignore[arg-type]
    client.set_streams([PUBLIC_STREAM])

    with pytest.raises(ZulipCrawlError, match="limited history"):
        list(client.get_source_data())


def test_message_client_rejects_non_advancing_pagination() -> None:
    pull_client = StubPullClient(
        [
            {
                "result": "success",
                "messages": [{"id": 2, "stream_id": PUBLIC_STREAM.stream_id}],
                "found_newest": False,
            },
            {
                "result": "success",
                "messages": [{"id": 2, "stream_id": PUBLIC_STREAM.stream_id}],
                "found_newest": False,
            },
        ]
    )
    client = ZulipMessageDataClient(pull_client)  # type: ignore[arg-type]
    client.set_streams([PUBLIC_STREAM])

    with pytest.raises(ZulipCrawlError, match="stopped advancing"):
        list(client.get_source_data())


def test_identity_client_fails_closed_without_private_member_delivery_email() -> None:
    pull_client = StubPullClient(
        [
            {
                "result": "success",
                "streams": [
                    {
                        "stream_id": PRIVATE_STREAM.stream_id,
                        "name": PRIVATE_STREAM.name,
                        "invite_only": True,
                    }
                ],
            },
            {
                "result": "success",
                "members": [
                    {
                        "user_id": USER.user_id,
                        "email": USER.email,
                        "delivery_email": None,
                        "full_name": USER.full_name,
                        "is_active": True,
                        "is_bot": False,
                    }
                ],
            },
            {
                "result": "success",
                "subscribers": [USER.user_id],
            },
        ]
    )

    with pytest.raises(ZulipCrawlError, match="no visible delivery_email"):
        ZulipIdentityClient(pull_client).fetch_context()  # type: ignore[arg-type]


def test_transform_maps_public_and_private_permissions() -> None:
    connector = _connector([], _context(private=True))
    connector._context = _context(private=True)

    public_document, private_document = connector.transform(
        [
            _message(1, PUBLIC_STREAM),
            _message(2, PRIVATE_STREAM),
        ]
    )

    assert public_document.id == "zulip-message-1"
    assert public_document.title == "#engineering > search"
    assert public_document.view_url == "https://example.zulipchat.com/#narrow/channel/10/near/1"
    assert public_document.author is not None
    assert public_document.permissions is not None
    assert private_document.permissions is not None
    assert public_document.author.datasource_user_id == str(USER.user_id)
    assert public_document.permissions.allow_all_datasource_users_access is True
    assert private_document.permissions.allowed_groups == ["zulip-channel-20"]


def test_transform_rejects_private_message_without_validated_memberships() -> None:
    connector = _connector([], _context())
    connector._context = _context()

    with pytest.raises(ZulipCrawlError, match="no validated membership data"):
        connector.transform([_message(2, PRIVATE_STREAM)])


def test_full_connector_run_uploads_identities_permissions_and_documents() -> None:
    context = _context(private=True)
    connector = _connector(
        [
            _message(1, PUBLIC_STREAM),
            _message(2, PRIVATE_STREAM),
        ],
        context,
    )
    connector.batch_size = 1

    client = run_connector(connector, options=ConnectorOptions(force_restart=True))

    client.assert_users_posted(1)
    client.assert_groups_posted(1)
    client.assert_memberships_posted(1)
    client.assert_documents_posted(2)
    assert connector.observability.get_metrics_summary()["documents_indexed"] == 2


def test_incremental_mode_is_rejected_before_source_or_upload_calls() -> None:
    connector = _connector([], _context())

    with pytest.raises(ValueError, match="Incremental"):
        connector.index_data(mode=IndexingMode.INCREMENTAL)
