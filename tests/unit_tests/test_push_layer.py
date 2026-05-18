"""Tests for the SDK push layer."""

from unittest.mock import MagicMock

from glean.api_client.models import ContentDefinition, DocumentDefinition
from glean.indexing.push.batching import iter_sized_batches, json_size_bytes
from glean.indexing.push.options import PushOptions
from glean.indexing.push.uploader import PushUploader


class _ClientContext:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc, tb):
        return None


class _ClientFactory:
    def __init__(self, client):
        self.client = client

    def __call__(self):
        return _ClientContext(self.client)


def _doc(doc_id: str, content: str = "hello") -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        title=f"Doc {doc_id}",
        datasource="test",
        view_url=f"https://example.com/{doc_id}",
        body=ContentDefinition(mime_type="text/plain", text_content=content),
    )


def test_sized_batches_respect_item_count_and_byte_limit():
    items = [
        {"id": "a", "payload": "x" * 20},
        {"id": "b", "payload": "x" * 20},
        {"id": "c", "payload": "x" * 20},
    ]

    batches = list(
        iter_sized_batches(
            items, max_items=10, max_bytes=json_size_bytes(items[0]) + 1, size_fn=json_size_bytes
        )
    )

    assert [len(batch) for batch in batches] == [1, 1, 1]


def test_bulk_document_upload_keeps_first_and_last_batches_blocking():
    client = MagicMock()
    uploader = PushUploader(_ClientFactory(client))
    docs = [_doc(str(i)) for i in range(4)]

    result = uploader.upload_documents(
        datasource="test",
        documents=docs,
        batch_size=1,
        options=PushOptions(upload_concurrency=2, document_batch_max_bytes=None),
        upload_id="upload-1",
    )

    calls = client.indexing.documents.bulk_index.call_args_list
    assert result.operation == "bulkindexdocuments"
    assert result.item_count == 4
    assert result.batch_count == 4
    assert result.upload_id == "upload-1"
    assert len(calls) == 4

    assert calls[0].kwargs["is_first_page"] is True
    assert calls[0].kwargs["is_last_page"] is False
    assert calls[-1].kwargs["is_first_page"] is False
    assert calls[-1].kwargs["is_last_page"] is True
    for call in calls[1:-1]:
        assert call.kwargs["is_first_page"] is False
        assert call.kwargs["is_last_page"] is False


def test_bulk_document_upload_forwards_retry_and_timeout_options():
    retry_config = object()
    client = MagicMock()
    uploader = PushUploader(_ClientFactory(client))

    uploader.upload_documents(
        datasource="test",
        documents=[_doc("1")],
        batch_size=10,
        options=PushOptions(retries=retry_config, upload_timeout_ms=120_000),
        upload_id="upload-1",
    )

    call = client.indexing.documents.bulk_index.call_args
    assert call.kwargs["retries"] is retry_config
    assert call.kwargs["timeout_ms"] == 120_000


def test_incremental_document_upload_uses_indexdocuments():
    client = MagicMock()
    uploader = PushUploader(_ClientFactory(client))

    result = uploader.index_documents(
        datasource="test",
        documents=[_doc("1"), _doc("2")],
        batch_size=10,
        options=PushOptions(document_batch_max_bytes=None),
        upload_id="incremental-1",
    )

    client.indexing.documents.index.assert_called_once()
    call = client.indexing.documents.index.call_args
    assert call.kwargs["datasource"] == "test"
    assert call.kwargs["upload_id"] == "incremental-1"
    assert len(call.kwargs["documents"]) == 2
    assert result.operation == "indexdocuments"
    assert result.item_count == 2


def test_incremental_identity_and_permission_operations_are_wrapped():
    client = MagicMock()
    uploader = PushUploader(_ClientFactory(client))
    options = PushOptions()

    uploader.index_users(datasource="test", users=[{"email": "a@example.com"}], options=options)
    uploader.index_groups(datasource="test", groups=[{"name": "g"}], options=options)
    uploader.index_memberships(
        datasource="test",
        memberships=[{"group": "g", "memberUserId": "a@example.com"}],
        options=options,
    )
    uploader.update_permissions(
        datasource="test", id="doc-1", permissions={"allowAnonymousAccess": True}, options=options
    )
    uploader.delete_document(datasource="test", object_type="Article", id="doc-1", options=options)
    uploader.delete_user(datasource="test", email="a@example.com", options=options)
    uploader.delete_group(datasource="test", group_name="g", options=options)
    uploader.delete_membership(
        datasource="test",
        membership={"group": "g", "memberUserId": "a@example.com"},
        options=options,
    )
    uploader.delete_employee(employee_email="a@example.com", options=options)

    client.indexing.permissions.index_user.assert_called_once()
    client.indexing.permissions.index_group.assert_called_once()
    client.indexing.permissions.index_membership.assert_called_once()
    client.indexing.permissions.update_permissions.assert_called_once()
    client.indexing.documents.delete.assert_called_once()
    client.indexing.permissions.delete_user.assert_called_once()
    client.indexing.permissions.delete_group.assert_called_once()
    client.indexing.permissions.delete_membership.assert_called_once()
    client.indexing.people.delete.assert_called_once()
