"""Tests for incremental push uploader wrappers."""

from glean.api_client.models import (
    ContentDefinition,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceMembershipDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
    EmployeeInfoDefinition,
)

from glean.indexing.push import PushUploader
from glean.indexing.testing import mock_glean_client


def _document(document_id: str = "doc-1") -> DocumentDefinition:
    return DocumentDefinition(
        datasource="test_datasource",
        id=document_id,
        title=f"Doc {document_id}",
        view_url=f"https://example.com/{document_id}",
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


def test_bulk_index_documents_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    documents = [_document("doc-1"), _document("doc-2")]

    with mock_glean_client() as client:
        uploader.bulk_index_documents(
            documents,
            upload_id="upload-1",
            batch_size=1,
            force_restart_upload=True,
            disable_stale_document_deletion_check=True,
        )

    assert client.indexing.documents.bulk_index.call_count == 2
    client.indexing.documents.bulk_index.assert_any_call(
        datasource="test_datasource",
        documents=[documents[0]],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=False,
        force_restart_upload=True,
        disable_stale_document_deletion_check=None,
    )
    client.indexing.documents.bulk_index.assert_any_call(
        datasource="test_datasource",
        documents=[documents[1]],
        upload_id="upload-1",
        is_first_page=False,
        is_last_page=True,
        force_restart_upload=None,
        disable_stale_document_deletion_check=True,
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


def test_bulk_index_users_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    user = DatasourceUserDefinition(email="user@example.com", name="User")

    with mock_glean_client() as client:
        uploader.bulk_index_users(
            [user],
            upload_id="upload-1",
            force_restart_upload=True,
            disable_stale_data_deletion_check=True,
        )

    client.indexing.permissions.bulk_index_users.assert_called_once_with(
        datasource="test_datasource",
        users=[user],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=True,
        force_restart_upload=True,
        disable_stale_data_deletion_check=True,
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


def test_bulk_index_groups_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    group = DatasourceGroupDefinition(name="engineering")

    with mock_glean_client() as client:
        uploader.bulk_index_groups(
            [group],
            upload_id="upload-1",
            force_restart_upload=True,
            disable_stale_data_deletion_check=True,
        )

    client.indexing.permissions.bulk_index_groups.assert_called_once_with(
        datasource="test_datasource",
        groups=[group],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=True,
        force_restart_upload=True,
        disable_stale_data_deletion_check=True,
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


def test_bulk_index_memberships_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    membership = DatasourceBulkMembershipDefinition(member_user_id="user@example.com")

    with mock_glean_client() as client:
        uploader.bulk_index_memberships(
            [membership],
            upload_id="upload-1",
            force_restart_upload=True,
            group="engineering",
        )

    client.indexing.permissions.bulk_index_memberships.assert_called_once_with(
        datasource="test_datasource",
        memberships=[membership],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=True,
        force_restart_upload=True,
        group="engineering",
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


def test_bulk_index_employees_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    employee = EmployeeInfoDefinition(
        email="user@example.com",
        first_name="User",
        last_name="Example",
        department="Engineering",
    )

    with mock_glean_client() as client:
        uploader.bulk_index_employees(
            [employee],
            upload_id="upload-1",
            force_restart_upload=True,
            disable_stale_data_deletion_check=True,
        )

    client.indexing.people.bulk_index.assert_called_once_with(
        employees=[employee],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=True,
        force_restart_upload=True,
        disable_stale_data_deletion_check=True,
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
