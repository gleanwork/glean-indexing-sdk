"""Tests for source-side pull HTTP recipes."""

from email.utils import formatdate
from time import time

import httpx
import pytest

from recipes.pull import PullHttpClient, PullHttpError, PullOptions, PullRetryOptions


def _fast_options(max_attempts: int = 2) -> PullOptions:
    return PullOptions(
        retries=PullRetryOptions(
            max_attempts=max_attempts,
            initial_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_seconds=0,
        )
    )


def test_http_client_uses_base_url_headers_and_parses_json(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/items?limit=1",
        json={"items": [{"id": "item-1"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(
        base_url="https://example.com/v1",
        headers={"Accept": "application/json", "Authorization": "Bearer token-1"},
        options=_fast_options(),
    )

    response = client.get("/items", params={"limit": 1})

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Authorization"] == "Bearer token-1"
    assert response.status_code == 200
    assert response.json_dict()["items"][0]["id"] == "item-1"


def test_http_client_accepts_absolute_urls_for_followed_links(httpx_mock):
    httpx_mock.add_response(
        url="https://cdn.example.net/page-2",
        json={"items": [{"id": "item-2"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    response = client.get("https://cdn.example.net/page-2")

    assert response.json_dict()["items"][0]["id"] == "item-2"


def test_http_client_retries_retryable_status_and_uses_retry_after(httpx_mock):
    sleeps: list[float] = []
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        status_code=429,
        headers={"Retry-After": "2"},
    )
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        json={"items": [{"id": "item-1"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options(), sleep=sleeps.append)
    response = client.get("/items")

    assert response.json_dict()["items"][0]["id"] == "item-1"
    assert sleeps == [2.0]
    assert len(httpx_mock.get_requests()) == 2


def test_http_client_parses_http_date_retry_after(httpx_mock):
    sleeps: list[float] = []
    retry_after = formatdate(time() + 60, usegmt=True)
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        status_code=503,
        headers={"Retry-After": retry_after},
    )
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        json={"items": []},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options(), sleep=sleeps.append)
    client.get("/items")

    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 60


def test_http_client_does_not_retry_non_retryable_status(httpx_mock):
    httpx_mock.add_response(url="https://example.com/v1/items", status_code=400, text="bad request")

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())

    with pytest.raises(PullHttpError) as exc_info:
        client.get("/items")

    assert exc_info.value.status_code == 400
    assert len(httpx_mock.get_requests()) == 1


def test_http_client_retries_transport_errors(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("temporary failure"))
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        json={"items": [{"id": "item-1"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options(), sleep=lambda _: None)
    response = client.get("/items")

    assert response.json_dict()["items"][0]["id"] == "item-1"
    assert len(httpx_mock.get_requests()) == 2


def test_http_client_can_disable_transport_error_retries(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("temporary failure"))
    options = _fast_options()
    options.retries.retry_connection_errors = False

    client = PullHttpClient(base_url="https://example.com/v1", options=options)

    with pytest.raises(PullHttpError, match="temporary failure"):
        client.get("/items")

    assert len(httpx_mock.get_requests()) == 1


def test_http_client_parses_text_response(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/status",
        text="ok",
        headers={"Content-Type": "text/plain"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    response = client.get("/status")

    assert response.data == "ok"
    assert response.content == b"ok"


def test_http_client_rejects_invalid_json(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        text="{not-json",
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())

    with pytest.raises(PullHttpError, match="invalid JSON"):
        client.get("/items")


def test_response_json_helpers_validate_shape(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        json=[{"id": "item-1"}],
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    response = client.get("/items")

    assert response.json_list()[0]["id"] == "item-1"
    with pytest.raises(TypeError, match="Expected JSON object"):
        response.json_dict()


def test_paginate_yields_responses_across_link_header(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/items?limit=1",
        json={"items": [{"id": "item-1"}]},
        headers={
            "Content-Type": "application/json",
            "Link": '<https://example.com/v1/items?page=2>; rel="next"',
        },
    )
    httpx_mock.add_response(
        url="https://example.com/v1/items?page=2",
        json={"items": [{"id": "item-2"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    pages = list(client.paginate("/items", params={"limit": 1}))

    assert [page.json_dict()["items"][0]["id"] for page in pages] == ["item-1", "item-2"]


def test_paginate_accepts_custom_next_page_resolver(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/items",
        json={"items": [{"id": "item-1"}], "next": "/items?page=2"},
        headers={"Content-Type": "application/json"},
    )
    httpx_mock.add_response(
        url="https://example.com/v1/items?page=2",
        json={"items": [{"id": "item-2"}], "next": None},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    pages = list(client.paginate("/items", next_page=lambda response: response.json_dict()["next"]))

    assert [item["id"] for page in pages for item in page.json_dict()["items"]] == ["item-1", "item-2"]


def test_get_bytes_applies_size_cap(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/file",
        content=b"abcdef",
        headers={"Content-Type": "application/octet-stream"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_options())
    content, content_type = client.get_bytes("/file", max_bytes=3)

    assert content == b"abc"
    assert content_type == "application/octet-stream"


def test_http_client_context_manager_does_not_close_injected_client():
    inner_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})))
    pull_client = PullHttpClient(base_url="https://example.com", client=inner_client)

    with pull_client:
        assert not inner_client.is_closed

    assert not inner_client.is_closed
