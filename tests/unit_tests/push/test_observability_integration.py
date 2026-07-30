"""Tests for push-layer observability integration."""

from unittest.mock import MagicMock, patch
from typing import cast

import pytest
from glean.api_client.models import DatasourceGroupDefinition, DatasourceUserDefinition, DocumentDefinition

from glean.indexing.observability import ConnectorObservability
from glean.indexing.push import PushUploader


class RecordingObservability:
    def __init__(self) -> None:
        self.batch_starts: list[dict] = []
        self.batch_completions: list[dict] = []
        self.batch_failures: list[dict] = []
        self.batch_sizes: list[int] = []
        self.api_counts: list[str] = []
        self.api_latencies: list[str] = []
        self.api_errors: list[tuple[str, str]] = []
        self.document_starts: list[dict] = []
        self.document_completions: list[dict] = []

    def log_batch_upload_started(self, **kwargs):
        self.batch_starts.append(kwargs)

    def log_batch_upload_completed(self, **kwargs):
        self.batch_completions.append(kwargs)

    def log_batch_upload_failed(self, **kwargs):
        self.batch_failures.append(kwargs)

    def record_upload_batch_size(self, batch_size: int) -> None:
        self.batch_sizes.append(batch_size)

    def record_api_request_count(self, endpoint: str) -> None:
        self.api_counts.append(endpoint)

    def record_api_request_latency(self, latency_ms: float, endpoint: str) -> None:
        self.api_latencies.append(endpoint)

    def record_api_request_error(self, endpoint: str, error_type: str) -> None:
        self.api_errors.append((endpoint, error_type))

    def log_document_upload_started(self, document_ids, **kwargs):
        self.document_starts.append({"document_ids": document_ids, **kwargs})

    def log_document_upload_completed(self, document_ids, **kwargs):
        self.document_completions.append({"document_ids": document_ids, **kwargs})


class ClientContext:
    def __init__(self, client: MagicMock) -> None:
        self.client = client

    def __enter__(self) -> MagicMock:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _doc(doc_id: str) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        title=f"Document {doc_id}",
        datasource="test_datasource",
        view_url=f"https://example.com/{doc_id}",
    )


def _user(email: str) -> DatasourceUserDefinition:
    return DatasourceUserDefinition(email=email, name=email)


def _group(name: str) -> DatasourceGroupDefinition:
    return DatasourceGroupDefinition(name=name)


def _observability_arg(observability: RecordingObservability) -> ConnectorObservability:
    return cast(ConnectorObservability, observability)


def test_bulk_document_upload_records_batch_lifecycle_and_api_metrics():
    client = MagicMock()
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        PushUploader("test_datasource", observability=_observability_arg(observability)).bulk_index_documents(
            [_doc("1"), _doc("2"), _doc("3")],
            upload_id="upload-1",
            batch_size=2,
            max_batch_bytes=None,
        )

    assert client.indexing.documents.bulk_index.call_count == 2
    assert [event["batch_index"] for event in observability.batch_starts] == [0, 1]
    assert [event["batch_count"] for event in observability.batch_starts] == [2, 2]
    assert [event["batch_size"] for event in observability.batch_starts] == [2, 1]
    assert [event["upload_id"] for event in observability.batch_completions] == ["upload-1", "upload-1"]
    assert observability.batch_sizes == [2, 1]
    assert observability.api_counts == ["documents.bulk_index", "documents.bulk_index"]
    assert observability.api_latencies == ["documents.bulk_index", "documents.bulk_index"]
    assert observability.api_errors == []


def test_bulk_document_upload_records_failure_event_and_error_metric():
    client = MagicMock()
    error = RuntimeError("upload failed")
    client.indexing.documents.bulk_index.side_effect = error
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        with pytest.raises(RuntimeError, match="upload failed"):
            PushUploader(
                "test_datasource",
                observability=_observability_arg(observability),
            ).bulk_index_single_batch_upload(
                [_doc("1")],
                upload_id="upload-1",
                is_first_page=True,
                is_last_page=True,
            )

    assert observability.batch_failures[0]["batch_index"] == 0
    assert observability.batch_failures[0]["batch_count"] == 1
    assert observability.batch_failures[0]["error"] is error
    assert observability.api_errors == [("documents.bulk_index", "RuntimeError")]


def test_index_documents_records_document_upload_lifecycle_and_api_metrics():
    client = MagicMock()
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        PushUploader("test_datasource", observability=_observability_arg(observability)).index_documents(
            [_doc("1"), _doc("2")],
            upload_id="upload-1",
        )

    client.indexing.documents.index.assert_called_once()
    assert observability.document_starts == [{"document_ids": ["1", "2"], "upload_id": "upload-1"}]
    assert observability.document_completions[0]["document_ids"] == ["1", "2"]
    assert observability.document_completions[0]["upload_id"] == "upload-1"
    assert observability.api_counts == ["documents.index"]
    assert observability.api_latencies == ["documents.index"]


def test_bulk_user_upload_records_batch_lifecycle_and_api_metrics():
    client = MagicMock()
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        PushUploader("test_datasource", observability=_observability_arg(observability)).bulk_index_users(
            [_user("a@example.com"), _user("b@example.com"), _user("c@example.com")],
            upload_id="upload-1",
            batch_size=2,
        )

    assert client.indexing.permissions.bulk_index_users.call_count == 2
    assert [event["entity_type"] for event in observability.batch_starts] == ["user", "user"]
    assert [event["batch_size"] for event in observability.batch_starts] == [2, 1]
    assert observability.batch_sizes == [2, 1]
    assert observability.api_counts == ["permissions.bulk_index_users", "permissions.bulk_index_users"]
    assert observability.api_latencies == ["permissions.bulk_index_users", "permissions.bulk_index_users"]


def test_bulk_group_upload_records_failure_event_and_error_metric():
    client = MagicMock()
    error = RuntimeError("group upload failed")
    client.indexing.permissions.bulk_index_groups.side_effect = error
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        with pytest.raises(RuntimeError, match="group upload failed"):
            PushUploader("test_datasource", observability=_observability_arg(observability)).bulk_index_groups(
                [_group("group-1")],
                upload_id="upload-1",
            )

    assert observability.batch_failures[0]["entity_type"] == "group"
    assert observability.batch_failures[0]["error"] is error
    assert observability.api_errors == [("permissions.bulk_index_groups", "RuntimeError")]


def test_single_and_delete_permission_calls_record_api_metrics():
    client = MagicMock()
    observability = RecordingObservability()

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext(client)):
        uploader = PushUploader("test_datasource", observability=_observability_arg(observability))
        uploader.index_user(_user("a@example.com"))
        uploader.delete_user(email="a@example.com")

    client.indexing.permissions.index_user.assert_called_once()
    client.indexing.permissions.delete_user.assert_called_once()
    assert observability.api_counts == ["permissions.index_user", "permissions.delete_user"]
    assert observability.api_latencies == ["permissions.index_user", "permissions.delete_user"]
