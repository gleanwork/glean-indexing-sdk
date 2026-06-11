"""Tests for incremental push uploader wrappers."""

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceMembershipDefinition,
    DatasourceUserDefinition,
    DebugDocumentRequest,
    DocumentDefinition,
    EmployeeInfoDefinition,
)

from glean.indexing import StatusClient as TopLevelStatusClient
from glean.indexing.push import PushUploader, StatusClient
from glean.indexing.testing import mock_glean_client


def _document(document_id: str = "doc-1") -> DocumentDefinition:
    return DocumentDefinition(
        datasource="test_datasource",
        id=document_id,
        title=f"Doc {document_id}",
        view_url=f"https://example.com/{document_id}",
        body=ContentDefinition(mime_type="text/plain", text_content="hello"),
    )


def test_configure_datasource_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    config = CustomDatasourceConfig(
        name="test_datasource",
        display_name="Test Datasource",
        url_regex=r"https://example\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    with mock_glean_client() as client:
        uploader.configure_datasource(config)

    client.indexing.datasources.add.assert_called_once()
    call_args = client.indexing.datasources.add.call_args[1]
    assert call_args["name"] == "test_datasource"
    assert call_args["display_name"] == "Test Datasource"
    assert call_args["url_regex"] == r"https://example\.com/.*"
    assert call_args["trust_url_regex_for_view_activity"] is True


def test_status_client_is_exported_from_top_level_package():
    assert TopLevelStatusClient is StatusClient


def test_get_datasource_status_calls_generated_client():
    status_client = StatusClient(datasource="test_datasource")

    with mock_glean_client() as client:
        status_client.get_datasource_status()

    client.indexing.datasource.status.assert_called_once_with(datasource="test_datasource")


def test_get_document_status_calls_generated_client():
    status_client = StatusClient(datasource="test_datasource")

    with mock_glean_client() as client:
        status_client.get_document_status(object_type="Article", document_id="doc-1")

    client.indexing.documents.debug.assert_called_once_with(
        datasource="test_datasource",
        object_type="Article",
        doc_id="doc-1",
    )


def test_get_documents_status_calls_generated_client():
    status_client = StatusClient(datasource="test_datasource")
    documents = [
        DebugDocumentRequest(objectType="Article", docId="doc-1"),
        DebugDocumentRequest(objectType="Article", docId="doc-2"),
    ]

    with mock_glean_client() as client:
        status_client.get_documents_status(documents)

    client.indexing.documents.debug_many.assert_called_once_with(
        datasource="test_datasource",
        debug_documents=documents,
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


def test_bulk_index_documents_splits_batches_by_byte_size():
    uploader = PushUploader(datasource="test_datasource")
    documents = [_document("doc-1"), _document("doc-2")]

    with mock_glean_client() as client:
        uploader.bulk_index_documents(
            documents,
            upload_id="upload-1",
            batch_size=10,
            max_batch_bytes=1,
            force_restart_upload=True,
            disable_stale_document_deletion_check=True,
        )

    calls = client.indexing.documents.bulk_index.call_args_list
    assert len(calls) == 2
    first_call = calls[0][1]
    assert first_call["is_first_page"] is True
    assert first_call["is_last_page"] is False
    assert first_call["force_restart_upload"] is True
    assert first_call["disable_stale_document_deletion_check"] is None
    last_call = calls[1][1]
    assert last_call["is_first_page"] is False
    assert last_call["is_last_page"] is True
    assert last_call["force_restart_upload"] is None
    assert last_call["disable_stale_document_deletion_check"] is True


def test_bulk_index_single_batch_upload_calls_generated_client():
    uploader = PushUploader(datasource="test_datasource")
    document = _document()

    with mock_glean_client() as client:
        uploader.bulk_index_single_batch_upload(
            [document],
            upload_id="upload-1",
            is_first_page=True,
            is_last_page=False,
            force_restart_upload=True,
            disable_stale_document_deletion_check=False,
        )

    client.indexing.documents.bulk_index.assert_called_once_with(
        datasource="test_datasource",
        documents=[document],
        upload_id="upload-1",
        is_first_page=True,
        is_last_page=False,
        force_restart_upload=True,
        disable_stale_document_deletion_check=False,
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


def test_status_request_options_are_forwarded_when_configured():
    retries = {"strategy": "backoff"}
    status_client = StatusClient(
        datasource="test_datasource",
        retries=retries,
        server_url="https://example-be.glean.com",
        timeout_ms=120_000,
        http_headers={"X-Test": "true"},
    )

    with mock_glean_client() as client:
        status_client.get_datasource_status()

    client.indexing.datasource.status.assert_called_once_with(
        datasource="test_datasource",
        retries=retries,
        server_url="https://example-be.glean.com",
        timeout_ms=120_000,
        http_headers={"X-Test": "true"},
    )


def test_uploader_request_options_are_forwarded_when_configured():
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
