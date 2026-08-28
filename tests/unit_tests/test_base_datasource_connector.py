"""Tests for BaseDatasourceConnector."""

from threading import Event, Lock, Thread
from typing import List, Optional, Sequence
from unittest.mock import Mock, patch
from unittest.mock import call as mock_call

import pytest

from glean.api_client.models import (
    ContentDefinition,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
)
from glean.indexing.common.batch_processor import DEFAULT_DOCUMENT_BATCH_SIZE_BYTES
from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from glean.indexing.exceptions import InconsistentDataError
from glean.indexing.models import (
    DEFAULT_UPLOAD_MAX_WORKERS,
    ConnectorOptions,
    CustomDatasourceConfig,
    DatasourceIdentityDefinitions,
    IndexingMode,
)
from glean.indexing.push import PushUploader
from glean.indexing.testing import mock_glean_client


class MockDataClient(BaseDataClient[dict]):
    """Mock data client for testing."""

    def __init__(self, data: List[dict]):
        self.data = data

    def get_source_data(self, since=None) -> Sequence[dict]:
        return self.data


class TestDatasourceConnector(BaseDatasourceConnector[dict]):
    """Test implementation of BaseDatasourceConnector."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="testconnector",
        display_name="Test Connector",
        url_regex=r"https://test\.example\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    def transform(self, data: Sequence[dict]) -> List[DocumentDefinition]:
        documents = []
        for item in data:
            document = DocumentDefinition(
                id=item["id"],
                title=item["title"],
                datasource=self.name,
                view_url=item["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=item["content"]),
            )
            documents.append(document)
        return documents


class BatchBytesOverrideConnector(TestDatasourceConnector):
    """Connector with a custom document byte-limit policy."""

    @staticmethod
    def _resolve_max_batch_bytes(options: Optional[ConnectorOptions]) -> Optional[int]:
        return 1024


class TestBaseDatasourceConnector:
    """Test cases for BaseDatasourceConnector."""

    def test_connector_initialization(self):
        """Test that connector initializes correctly."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        assert connector.name == "test_connector"
        assert connector.display_name == "Test Connector"
        assert connector.data_client == data_client
        assert connector.batch_size == 1000

    def test_config_property(self):
        """Test that config property includes name and display_name."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        config = connector.configuration
        assert config.name == "testconnector"
        assert config.display_name == "Test Connector"
        assert config.url_regex == r"https://test\.example\.com/.*"
        assert config.trust_url_regex_for_view_activity is True

    @patch("glean.indexing.push.uploader.api_client")
    def test_configure_datasource(self, mock_api_client):
        """Test datasource configuration."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.configure_datasource()

        mock_client.indexing.datasources.add.assert_called_once()
        call_args = mock_client.indexing.datasources.add.call_args[1]
        assert call_args["name"] == "testconnector"
        assert call_args["display_name"] == "Test Connector"

    def test_get_data(self):
        """Test data retrieval from data client."""
        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        result = connector.get_data()
        assert result == test_data

    @patch("glean.indexing.connectors.base_connector.PushUploader")
    def test_identity_uploads_share_observable_uploader(self, mock_uploader):
        """All entity paths share one uploader with the connector's observability instance."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        users = [object()]
        groups = [object()]
        memberships = [object()]
        identities = DatasourceIdentityDefinitions(
            users=users,
            groups=groups,
            memberships=memberships,
        )

        with patch.object(connector, "get_identities", return_value=identities):
            connector.index_data()

        expected_uploader_call = mock_call(
            datasource="test_connector",
            timeout_ms=None,
            observability=connector.observability,
            upload_max_workers=DEFAULT_UPLOAD_MAX_WORKERS,
        )
        assert mock_uploader.call_args_list == [expected_uploader_call]
        mock_uploader.return_value.bulk_index_users.assert_called_once_with(
            users=users,
            batch_size=connector.batch_size,
            force_restart_upload=None,
            disable_stale_data_deletion_check=None,
        )
        mock_uploader.return_value.bulk_index_groups.assert_called_once_with(
            groups=groups,
            batch_size=connector.batch_size,
            force_restart_upload=None,
            disable_stale_data_deletion_check=None,
        )
        mock_uploader.return_value.bulk_index_memberships.assert_called_once_with(
            memberships=memberships,
            batch_size=connector.batch_size,
            force_restart_upload=None,
        )

    def test_memberships_upload_when_groups_are_empty(self):
        """Memberships are an independent identity payload, not a child of groups."""
        connector = TestDatasourceConnector(name="test_connector", data_client=MockDataClient([]))
        membership = DatasourceBulkMembershipDefinition(member_user_id="user@example.com")
        identities = DatasourceIdentityDefinitions(
            users=[],
            groups=[],
            memberships=[membership],
        )

        with patch.object(connector, "get_identities", return_value=identities):
            with mock_glean_client() as client:
                connector.index_data()

        client.assert_memberships_posted(count=1, datasource="test_connector")
        assert client.memberships_posted == [membership]

    def test_invalid_identity_payload_makes_no_api_calls(self):
        """The complete identity payload is validated before the first mutation."""
        connector = TestDatasourceConnector(name="test_connector", data_client=MockDataClient([]))
        identities = DatasourceIdentityDefinitions(
            users=[DatasourceUserDefinition(email="user@example.com", name="User")],
            groups=[DatasourceGroupDefinition(name="engineering")],
        )

        with patch.object(connector, "get_identities", return_value=identities):
            with mock_glean_client() as client:
                with pytest.raises(InconsistentDataError, match="no memberships"):
                    connector.index_data()

        client.indexing.permissions.bulk_index_users.assert_not_called()
        client.indexing.permissions.bulk_index_groups.assert_not_called()
        client.indexing.permissions.bulk_index_memberships.assert_not_called()
        client.indexing.documents.bulk_index.assert_not_called()

    @pytest.mark.parametrize(
        ("entity_type", "stale_deletion_parameter"),
        [
            ("documents", "disable_stale_document_deletion_check"),
            ("users", "disable_stale_data_deletion_check"),
            ("groups", "disable_stale_data_deletion_check"),
            ("memberships", None),
        ],
    )
    def test_bulk_upload_option_matrix(self, entity_type, stale_deletion_parameter):
        """Each endpoint receives every ConnectorOption supported by that endpoint."""
        data = []
        identities = DatasourceIdentityDefinitions(users=[])
        if entity_type == "documents":
            data = [
                {
                    "id": "1",
                    "title": "Doc",
                    "content": "Content",
                    "url": "https://test.example.com/1",
                }
            ]
        elif entity_type == "users":
            identities = DatasourceIdentityDefinitions(
                users=[DatasourceUserDefinition(email="user@example.com", name="User")]
            )
        elif entity_type == "groups":
            identities = DatasourceIdentityDefinitions(
                users=[],
                groups=[DatasourceGroupDefinition(name="engineering")],
                memberships=[DatasourceBulkMembershipDefinition(member_user_id="user@example.com")],
            )
        else:
            identities = DatasourceIdentityDefinitions(
                users=[],
                groups=[],
                memberships=[DatasourceBulkMembershipDefinition(member_user_id="user@example.com")],
            )

        connector = TestDatasourceConnector(name="test_connector", data_client=MockDataClient(data))
        options = ConnectorOptions(
            upload_timeout_ms=120_000,
            upload_max_workers=1,
            force_restart=True,
            disable_stale_deletion_check=True,
        )

        with patch.object(connector, "get_identities", return_value=identities):
            with mock_glean_client() as client:
                connector.index_data(options=options)

        calls = {
            "documents": client.indexing.documents.bulk_index,
            "users": client.indexing.permissions.bulk_index_users,
            "groups": client.indexing.permissions.bulk_index_groups,
            "memberships": client.indexing.permissions.bulk_index_memberships,
        }
        call_kwargs = calls[entity_type].call_args.kwargs
        assert call_kwargs["timeout_ms"] == 120_000
        assert call_kwargs["force_restart_upload"] is True
        if stale_deletion_parameter:
            assert call_kwargs[stale_deletion_parameter] is True
        else:
            assert "disable_stale_document_deletion_check" not in call_kwargs
            assert "disable_stale_data_deletion_check" not in call_kwargs

    def test_incremental_upload_uses_additive_index_without_bulk_only_options(self):
        """Incremental crawls add/update documents without triggering replacement semantics."""
        data = [
            {
                "id": "1",
                "title": "Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        connector = TestDatasourceConnector(name="test_connector", data_client=MockDataClient(data))
        options = ConnectorOptions(
            upload_timeout_ms=120_000,
            force_restart=True,
            disable_stale_deletion_check=True,
        )

        with mock_glean_client() as client:
            connector.index_data(mode=IndexingMode.INCREMENTAL, options=options)

        client.indexing.documents.index.assert_called_once()
        call_kwargs = client.indexing.documents.index.call_args.kwargs
        assert call_kwargs["documents"][0].id == "1"
        assert call_kwargs["timeout_ms"] == 120_000
        assert "force_restart_upload" not in call_kwargs
        assert "disable_stale_document_deletion_check" not in call_kwargs
        client.indexing.documents.bulk_index.assert_not_called()

    def test_empty_incremental_upload_makes_no_document_call(self):
        connector = TestDatasourceConnector(
            name="test_connector",
            data_client=MockDataClient([]),
        )

        with mock_glean_client() as client:
            connector.index_data(mode=IndexingMode.INCREMENTAL)

        client.indexing.documents.index.assert_not_called()
        client.indexing.documents.bulk_index.assert_not_called()

    def test_empty_full_upload_reconciles_with_one_empty_bulk_page(self):
        connector = TestDatasourceConnector(
            name="test_connector",
            data_client=MockDataClient([]),
        )

        with mock_glean_client() as client:
            connector.index_data(mode=IndexingMode.FULL)

        client.indexing.documents.bulk_index.assert_called_once()
        call_kwargs = client.indexing.documents.bulk_index.call_args.kwargs
        assert call_kwargs["documents"] == []
        assert call_kwargs["is_first_page"] is True
        assert call_kwargs["is_last_page"] is True
        client.indexing.documents.index.assert_not_called()

    def test_document_upload_max_workers_limits_concurrency(self):
        """The public worker option controls PushUploader's middle-page concurrency."""
        data = [
            {
                "id": str(index),
                "title": f"Doc {index}",
                "content": "Content",
                "url": f"https://test.example.com/{index}",
            }
            for index in range(4)
        ]
        connector = TestDatasourceConnector(name="test_connector", data_client=MockDataClient(data))
        connector.batch_size = 1
        first_middle_started = Event()
        second_middle_started = Event()
        release_first_middle = Event()
        middle_call_lock = Lock()
        middle_call_count = 0
        errors = []

        def upload_batch(*args, **kwargs):
            nonlocal middle_call_count
            if kwargs["is_first_page"] or kwargs["is_last_page"]:
                return
            with middle_call_lock:
                middle_call_count += 1
                call_number = middle_call_count
            if call_number == 1:
                first_middle_started.set()
                assert release_first_middle.wait(timeout=2)
            else:
                second_middle_started.set()

        def index_data():
            try:
                connector.index_data(options=ConnectorOptions(upload_max_workers=1))
            except BaseException as error:
                errors.append(error)

        with patch.object(PushUploader, "bulk_index_single_batch_upload", side_effect=upload_batch):
            thread = Thread(target=index_data)
            thread.start()
            assert first_middle_started.wait(timeout=2)
            assert not second_middle_started.wait(timeout=0.1)
            release_first_middle.set()
            thread.join(timeout=2)

        assert not thread.is_alive()
        assert errors == []
        assert second_middle_started.is_set()

    def test_transform(self):
        """Test data transformation."""
        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        documents = connector.transform(test_data)

        assert len(documents) == 1
        doc = documents[0]
        assert doc.id == "1"
        assert doc.title == "Test Doc"
        assert doc.datasource == "test_connector"
        assert doc.view_url == "https://test.example.com/1"
        assert doc.body and doc.body.text_content == "Content"

    def test_get_last_crawl_timestamp(self):
        """Test that default timestamp is None."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        timestamp = connector._get_last_crawl_timestamp()
        assert timestamp is None

    @patch("glean.indexing.push.uploader.api_client")
    def test_force_restart_upload(self, mock_api_client):
        """Test that force_restart option sets force_restart_upload on first batch."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Test Doc 1",
                "content": "Content 1",
                "url": "https://test.example.com/1",
            },
            {
                "id": "2",
                "title": "Test Doc 2",
                "content": "Content 2",
                "url": "https://test.example.com/2",
            },
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        connector.batch_size = 1

        connector.index_data(options=ConnectorOptions(force_restart=True))

        # Should be called twice (one batch per document)
        assert mock_client.indexing.documents.bulk_index.call_count == 2

        # First call should have force_restart_upload=True
        first_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[0][1]
        assert first_call_kwargs["force_restart_upload"] is True
        assert first_call_kwargs["is_first_page"] is True
        assert first_call_kwargs["is_last_page"] is False

        # Second call should have force_restart_upload=None
        second_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[1][1]
        assert second_call_kwargs["force_restart_upload"] is None
        assert second_call_kwargs["is_first_page"] is False
        assert second_call_kwargs["is_last_page"] is True

    @patch("glean.indexing.push.uploader.api_client")
    def test_normal_upload_no_force_restart(self, mock_api_client):
        """Test that normal upload does not set force_restart_upload."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data()

        # Should be called once
        assert mock_client.indexing.documents.bulk_index.call_count == 1

        call_kwargs = mock_client.indexing.documents.bulk_index.call_args[1]
        assert call_kwargs["force_restart_upload"] is None
        assert call_kwargs["is_first_page"] is True
        assert call_kwargs["is_last_page"] is True

    @patch("glean.indexing.push.uploader.api_client")
    def test_disable_stale_deletion_check_on_last_page_only(self, mock_api_client):
        """Test that disable_stale_document_deletion_check is set only on the last batch."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Doc 1",
                "content": "Content 1",
                "url": "https://test.example.com/1",
            },
            {
                "id": "2",
                "title": "Doc 2",
                "content": "Content 2",
                "url": "https://test.example.com/2",
            },
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        connector.batch_size = 1

        connector.index_data(options=ConnectorOptions(disable_stale_deletion_check=True))

        assert mock_client.indexing.documents.bulk_index.call_count == 2

        first_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[0][1]
        assert first_call_kwargs["disable_stale_document_deletion_check"] is None

        last_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[1][1]
        assert last_call_kwargs["disable_stale_document_deletion_check"] is True

    @patch("glean.indexing.push.uploader.api_client")
    def test_disable_stale_deletion_check_not_set_without_options(self, mock_api_client):
        """Test that disable_stale_document_deletion_check is not set when options are not provided."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {"id": "1", "title": "Doc", "content": "Content", "url": "https://test.example.com/1"},
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data()

        call_kwargs = mock_client.indexing.documents.bulk_index.call_args[1]
        assert call_kwargs["disable_stale_document_deletion_check"] is None

    @patch("glean.indexing.push.uploader.api_client")
    def test_upload_timeout_ms_passed_to_bulk_index(self, mock_api_client):
        """Test that upload_timeout_ms is forwarded to every bulk_index call."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Doc 1",
                "content": "Content 1",
                "url": "https://test.example.com/1",
            },
            {
                "id": "2",
                "title": "Doc 2",
                "content": "Content 2",
                "url": "https://test.example.com/2",
            },
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        connector.batch_size = 1

        connector.index_data(options=ConnectorOptions(upload_timeout_ms=120_000))

        assert mock_client.indexing.documents.bulk_index.call_count == 2
        for call in mock_client.indexing.documents.bulk_index.call_args_list:
            assert call[1]["timeout_ms"] == 120_000

    @patch("glean.indexing.push.uploader.api_client")
    def test_upload_timeout_ms_defaults_to_none(self, mock_api_client):
        """Test that timeout_ms is None when no options are provided (SDK default applies)."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {"id": "1", "title": "Doc", "content": "Content", "url": "https://test.example.com/1"},
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data()

        call_kwargs = mock_client.indexing.documents.bulk_index.call_args[1]
        assert call_kwargs.get("timeout_ms") is None

    @patch("glean.indexing.connectors.base_connector.PushUploader")
    def test_document_batch_size_bytes_forwarded_as_max_batch_bytes(self, mock_uploader):
        """Test that ConnectorOptions.document_batch_size_bytes reaches the uploader."""
        test_data = [
            {"id": "1", "title": "Doc", "content": "Content", "url": "https://test.example.com/1"},
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data(options=ConnectorOptions(document_batch_size_bytes=2048))

        call_kwargs = mock_uploader.return_value.bulk_index_documents.call_args[1]
        assert call_kwargs["max_batch_bytes"] == 2048

    @patch("glean.indexing.connectors.base_connector.PushUploader")
    def test_document_batch_size_bytes_uses_connector_override(self, mock_uploader):
        """Centralized endpoint options preserve the connector's byte-limit override."""
        test_data = [
            {"id": "1", "title": "Doc", "content": "Content", "url": "https://test.example.com/1"},
        ]
        connector = BatchBytesOverrideConnector(
            name="test_connector", data_client=MockDataClient(test_data)
        )

        connector.index_data(options=ConnectorOptions(document_batch_size_bytes=2048))

        call_kwargs = mock_uploader.return_value.bulk_index_documents.call_args[1]
        assert call_kwargs["max_batch_bytes"] == 1024

    @patch("glean.indexing.connectors.base_connector.PushUploader")
    def test_document_batch_size_bytes_defaults_without_options(self, mock_uploader):
        """Test that omitting options still applies the uploader's default byte limit."""
        test_data = [
            {"id": "1", "title": "Doc", "content": "Content", "url": "https://test.example.com/1"},
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data()

        call_kwargs = mock_uploader.return_value.bulk_index_documents.call_args[1]
        assert call_kwargs["max_batch_bytes"] == DEFAULT_DOCUMENT_BATCH_SIZE_BYTES

    @patch("glean.indexing.push.uploader.api_client")
    def test_document_batch_size_bytes_splits_oversized_documents(self, mock_api_client):
        """Regression test: document_batch_size_bytes must split documents that would
        otherwise fit in a single count-based batch."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Doc 1",
                "content": "x" * 200,
                "url": "https://test.example.com/1",
            },
            {
                "id": "2",
                "title": "Doc 2",
                "content": "y" * 200,
                "url": "https://test.example.com/2",
            },
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        # Count-based batch size alone would fit both documents in a single upload.
        connector.batch_size = 10

        connector.index_data(options=ConnectorOptions(document_batch_size_bytes=100))

        assert mock_client.indexing.documents.bulk_index.call_count == 2

        first_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[0][1]
        assert len(first_call_kwargs["documents"]) == 1
        assert first_call_kwargs["is_first_page"] is True
        assert first_call_kwargs["is_last_page"] is False

        last_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[1][1]
        assert len(last_call_kwargs["documents"]) == 1
        assert last_call_kwargs["is_first_page"] is False
        assert last_call_kwargs["is_last_page"] is True
