"""HTTP-boundary regressions for live indexing status responses."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from glean.api_client import Glean
from glean.api_client.errors import GleanError
from glean.api_client.models import DebugDocumentRequest
from glean.indexing.push import StatusClient

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "status"


def _generated_client(body: str, *, status_code: int = 200) -> Glean:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text=body,
            headers={"Content-Type": "application/json"},
            request=request,
        )

    return Glean(
        api_token="test-token",
        server_url="https://example-be.glean.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_datasource_status_accepts_live_application_json_response():
    client = _generated_client((_FIXTURES / "datasource_status_200.json").read_text())

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        response = StatusClient("smoketest").get_datasource_status()

    assert response.documents is not None
    assert response.documents.counts is not None
    assert response.documents.counts.indexed is not None
    assert response.documents.counts.indexed[0].count == 2


def test_document_status_accepts_live_application_json_response():
    client = _generated_client((_FIXTURES / "document_status_200.json").read_text())

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        response = StatusClient("smoketest").get_documents_status(
            [DebugDocumentRequest(object_type="smokeDocument", doc_id="document-a")]
        )

    assert response.document_statuses is not None
    assert response.document_statuses[0].debug_info is not None
    assert response.document_statuses[0].debug_info.status is not None
    assert response.document_statuses[0].debug_info.status.indexing_status == "INDEXED"


def test_status_does_not_recover_malformed_http_200_json():
    client = _generated_client('{"documents": "not-a-status"}')

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        with pytest.raises(Exception):
            StatusClient("smoketest").get_datasource_status()


def test_status_does_not_recover_non_success_response():
    client = _generated_client('{"error": "unauthorized"}', status_code=401)

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        with pytest.raises(GleanError) as error:
            StatusClient("smoketest").get_datasource_status()

    assert error.value.status_code == 401
