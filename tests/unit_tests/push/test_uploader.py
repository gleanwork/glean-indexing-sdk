"""Tests for incremental push uploader wrappers."""

from glean.api_client.models import (
    ContentDefinition,
    DatasourceGroupDefinition,
    DatasourceMembershipDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
)

from glean.indexing.push import PushUploader
from glean.indexing.testing import mock_glean_client


def _document() -> DocumentDefinition:
    return DocumentDefinition(
        datasource="test_datasource",
        id="doc-1",
        title="Doc 1",
        view_url="https://example.com/doc-1",
        body=ContentDefinition(mime_type="text/plain", text_content="hello"),
    )


def test_index_documents_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    document = _document()

    with mock_glean_client() as client:
        uploader.index_documents([document], upload_id="upload-1")

    client.indexing.documents.index.assert_called_once_with(
        datasource="test_datasource",
        documents=[document],
        upload_id="upload-1",
    )


def test_delete_document_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")

    with mock_glean_client() as client:
        uploader.delete_document(object_type="Article", document_id="doc-1", version=3)

    client.indexing.documents.delete.assert_called_once_with(
        datasource="test_datasource",
        object_type="Article",
        id="doc-1",
        version=3,
    )


def test_index_user_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    user = DatasourceUserDefinition(email="user@example.com", name="User")

    with mock_glean_client() as client:
        uploader.index_user(user, version=3)

    client.indexing.permissions.index_user.assert_called_once_with(
        datasource="test_datasource",
        user=user,
        version=3,
    )


def test_index_group_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    group = DatasourceGroupDefinition(name="engineering")

    with mock_glean_client() as client:
        uploader.index_group(group, version=3)

    client.indexing.permissions.index_group.assert_called_once_with(
        datasource="test_datasource",
        group=group,
        version=3,
    )


def test_index_membership_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    membership = DatasourceMembershipDefinition(
        group_name="engineering", member_user_id="user@example.com"
    )

    with mock_glean_client() as client:
        uploader.index_membership(membership, version=3)

    client.indexing.permissions.index_membership.assert_called_once_with(
        datasource="test_datasource",
        membership=membership,
        version=3,
    )


def test_delete_user_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")

    with mock_glean_client() as client:
        uploader.delete_user(email="user@example.com", version=3)

    client.indexing.permissions.delete_user.assert_called_once_with(
        datasource="test_datasource",
        email="user@example.com",
        version=3,
    )


def test_delete_group_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")

    with mock_glean_client() as client:
        uploader.delete_group(group_name="engineering", version=3)

    client.indexing.permissions.delete_group.assert_called_once_with(
        datasource="test_datasource",
        group_name="engineering",
        version=3,
    )


def test_delete_membership_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    membership = DatasourceMembershipDefinition(
        group_name="engineering", member_user_id="user@example.com"
    )

    with mock_glean_client() as client:
        uploader.delete_membership(membership, version=3)

    client.indexing.permissions.delete_membership.assert_called_once_with(
        datasource="test_datasource",
        membership=membership,
        version=3,
    )


def test_request_options_are_forwarded_when_configured():
    retries = {"strategy": "backoff"}
    uploader = PushUploader(
        datasource="test_datasource",
        retries=retries,
        server_url="https://example-be.glean.com",
        timeout_ms=120_000,
        http_headers={"X-Test": "true"},
    )

    with mock_glean_client() as client:
        uploader.delete_user(email="user@example.com")

    client.indexing.permissions.delete_user.assert_called_once_with(
        datasource="test_datasource",
        email="user@example.com",
        version=None,
        retries=retries,
        server_url="https://example-be.glean.com",
        timeout_ms=120_000,
        http_headers={"X-Test": "true"},
    )
