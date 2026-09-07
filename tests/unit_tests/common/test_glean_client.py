"""Tests for the Glean API client helper."""

from unittest.mock import patch

import httpx
import pytest

import glean.indexing as indexing_module
from glean.api_client import Glean as GeneratedGlean
from glean.api_client.models import ContentDefinition, DocumentDefinition
from glean.indexing import __version__
from glean.indexing.common import glean_client as common_module
from glean.indexing.common.glean_client import DEFAULT_TIMEOUT_MS, api_client
from glean.indexing.exceptions import MissingEnvironmentVariableError
from glean.indexing.push import PushUploader, StatusClient


class TestApiClient:
    """Tests for api_client() helper."""

    def test_default_timeout_constant_is_60_seconds(self):
        """Confirm the documented default timeout is 60 seconds."""
        assert DEFAULT_TIMEOUT_MS == 60_000

    @patch.dict(
        "os.environ",
        {"GLEAN_SERVER_URL": "https://example.com", "GLEAN_INDEXING_API_TOKEN": "token"},
        clear=True,
    )
    @patch("glean.indexing.common.glean_client.Glean")
    def test_passes_default_timeout_when_using_server_url(self, mock_glean):
        """api_client() should pass DEFAULT_TIMEOUT_MS to Glean when using server_url."""
        api_client()

        mock_glean.assert_called_once_with(
            api_token="token",
            server_url="https://example.com",
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

    @patch.dict(
        "os.environ",
        {"GLEAN_INSTANCE": "my-instance", "GLEAN_INDEXING_API_TOKEN": "token"},
        clear=True,
    )
    @patch("glean.indexing.common.glean_client.Glean")
    def test_passes_default_timeout_when_using_instance(self, mock_glean):
        """api_client() should pass DEFAULT_TIMEOUT_MS to Glean when using deprecated instance."""
        api_client()

        mock_glean.assert_called_once_with(
            api_token="token",
            instance="my-instance",
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_when_required_env_vars_missing(self):
        """api_client() should raise when required env vars are missing."""
        with pytest.raises(MissingEnvironmentVariableError):
            api_client()


def _document() -> DocumentDefinition:
    return DocumentDefinition(
        datasource="test_datasource",
        id="doc-1",
        title="Document 1",
        view_url="https://example.com/doc-1",
        body=ContentDefinition(mime_type="text/plain", text_content="hello"),
    )


def test_api_client_uses_canonical_package_version_for_user_agent(monkeypatch):
    """Use the package's exported version when configuring the generated client."""
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://example-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "test-token")
    monkeypatch.setattr(indexing_module, "__version__", "canonical-test")

    with api_client() as client:
        assert client.sdk_configuration.user_agent == "glean-indexing-sdk/canonical-test"


def test_upload_and_status_requests_use_sdk_user_agent_and_preserve_headers(monkeypatch):
    """Upload and status requests share the SDK User-Agent and retain request headers."""
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://example-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "test-token")
    captured_requests: list[httpx.Request] = []
    http_clients: list[httpx.Client] = []

    def client_factory(**kwargs):
        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"documents": {}}, request=request)
            return httpx.Response(200, request=request)

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        http_clients.append(http_client)
        return GeneratedGlean(**kwargs, client=http_client)

    monkeypatch.setattr(common_module, "Glean", client_factory)
    headers = {"X-Test": "true"}
    original_headers = headers.copy()

    PushUploader(datasource="test_datasource", http_headers=headers).index_documents([_document()])
    StatusClient(datasource="test_datasource", http_headers=headers).get_datasource_status()

    assert len(captured_requests) == 2
    expected_user_agent = f"glean-indexing-sdk/{__version__}"
    for request in captured_requests:
        assert request.headers["User-Agent"] == expected_user_agent
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.headers["X-Test"] == "true"
        if "/indexdocuments" in request.url.path:
            assert request.headers["Accept"] == "*/*"
        else:
            assert request.headers["Accept"] == "application/json; charset=UTF-8"
        assert "X-Glean-Client" not in request.headers
    assert headers == original_headers

    for client in http_clients:
        client.close()
