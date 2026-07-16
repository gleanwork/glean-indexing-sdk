from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from typing import Any

import httpx
import pytest

from connectors.degreed.connector import (
    DegreedConnector,
    DegreedContentDataClient,
    DegreedContentRecord,
    DegreedCrawlError,
)
from glean.indexing.connectors import BaseStreamingDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing import run_connector


class StaticDegreedClient(BaseStreamingDataClient[DegreedContentRecord]):
    def __init__(self, records: Sequence[DegreedContentRecord]) -> None:
        self.records = records
        self.calls = 0

    def get_source_data(self, **kwargs: Any) -> Generator[DegreedContentRecord, None, None]:
        self.calls += 1
        yield from self.records


def _record(record_id: str = "content-1") -> Mapping[str, Any]:
    return {
        "type": "content",
        "id": record_id,
        "attributes": {
            "content-type": "Course",
            "title": "Advanced Search",
            "summary": "Learn how to build effective search experiences.",
            "url": "https://learning.example.com/search",
            "degreed-url": f"https://degreed.com/content/{record_id}",
            "format": "Online",
            "provider": "Example Academy",
            "language": "en",
            "learning-minutes": 45,
            "created-at": "2026-01-01T10:00:00Z",
            "modified-at": "2026-02-02T11:30:00Z",
        },
        "relationships": [
            {
                "Skill": {
                    "data": [
                        {"id": "Search", "type": "skill"},
                        {"id": "Information Retrieval", "type": "skill"},
                    ]
                }
            }
        ],
    }


def test_data_client_authenticates_and_follows_body_next_link() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-value", "expires_in": 3600})
        if request.url.params.get("next") == "page-2":
            return httpx.Response(200, json={"data": [_record("content-2")], "links": {"next": ""}})
        return httpx.Response(
            200,
            json={
                "data": [_record("content-1")],
                "links": {"next": "https://api.degreed.com/api/v2/content?limit=2&next=page-2"},
            },
        )

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = DegreedContentDataClient(
        "client-id",
        "client-secret",
        page_size=2,
        client=raw_client,
    )

    records = list(client.get_source_data())

    assert [record["id"] for record in records] == ["content-1", "content-2"]
    assert [request.url.path for request in requests] == [
        "/oauth/token",
        "/api/v2/content",
        "/api/v2/content",
    ]
    assert requests[1].headers["Authorization"] == "Bearer token-value"
    assert requests[1].url.params["limit"] == "2"
    assert requests[2].url.params["next"] == "page-2"
    assert "client-secret" not in str(requests[0].url)


def test_data_client_reuses_unexpired_access_token() -> None:
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if request.url.path == "/oauth/token":
            token_requests += 1
            return httpx.Response(200, json={"access_token": "token-value", "expires_in": 3600})
        return httpx.Response(200, json={"data": [], "links": {}})

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = DegreedContentDataClient("client-id", "client-secret", client=raw_client)

    assert list(client.get_source_data()) == []
    assert list(client.get_source_data()) == []
    assert token_requests == 1


def test_data_client_rejects_cross_origin_next_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-value", "expires_in": 3600})
        return httpx.Response(
            200,
            json={
                "data": [_record()],
                "links": {"next": "https://attacker.example/api/v2/content?next=secret"},
            },
        )

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = DegreedContentDataClient("client-id", "client-secret", client=raw_client)

    with pytest.raises(DegreedCrawlError, match="outside the configured API origin"):
        list(client.get_source_data())


def test_transform_maps_content_and_skills() -> None:
    connector = DegreedConnector(StaticDegreedClient([]))

    document = connector.transform([_record()])[0]

    assert document.id == "content-1"
    assert document.title == "Advanced Search"
    assert document.view_url == "https://degreed.com/content/content-1"
    assert document.object_type == "learning_content"
    assert document.body is not None
    assert document.body.text_content is not None
    assert "Learn how to build effective search experiences." in document.body.text_content
    assert "Skills: Search, Information Retrieval" in document.body.text_content
    assert document.summary is not None
    assert document.summary.text_content == "Learn how to build effective search experiences."
    assert document.tags == ["Course", "Example Academy", "en", "Search", "Information Retrieval"]
    assert document.custom_properties is not None
    assert {item.name: item.value for item in document.custom_properties}["skills"] == [
        "Search",
        "Information Retrieval",
    ]
    assert document.permissions is not None
    assert document.permissions.allow_all_datasource_users_access is True
    assert document.created_at == 1_767_261_600
    assert document.updated_at == 1_770_031_800


def test_transform_skips_records_without_required_search_fields() -> None:
    connector = DegreedConnector(StaticDegreedClient([]))
    missing_title = {
        **_record("missing-title"),
        "attributes": {**_record()["attributes"], "title": None},
    }

    documents = connector.transform([missing_title, {"id": "missing-attributes"}])

    assert documents == []
    assert connector.observability.get_metrics_summary()["documents_skipped"] == 2


def test_full_connector_run_uploads_documents() -> None:
    connector = DegreedConnector(StaticDegreedClient([_record("one"), _record("two")]))
    connector.batch_size = 1

    client = run_connector(connector, options=ConnectorOptions(force_restart=True))

    client.assert_documents_posted(2)
    assert connector.observability.get_metrics_summary()["documents_indexed"] == 2


def test_empty_full_crawl_finalizes_stale_document_deletion() -> None:
    connector = DegreedConnector(StaticDegreedClient([]))

    client = run_connector(connector, options=ConnectorOptions(force_restart=True))

    call = client.indexing.documents.bulk_index.call_args
    assert call is not None
    assert call.kwargs["documents"] == []
    assert call.kwargs["is_first_page"] is True
    assert call.kwargs["is_last_page"] is True


def test_incremental_mode_is_rejected_before_source_calls() -> None:
    data_client = StaticDegreedClient([])
    connector = DegreedConnector(data_client)

    with pytest.raises(ValueError, match="Incremental"):
        connector.index_data(mode=IndexingMode.INCREMENTAL)

    assert data_client.calls == 0
