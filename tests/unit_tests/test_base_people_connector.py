from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import EmployeeInfoDefinition
from glean.indexing.connectors.base_people_connector import BasePeopleConnector
from glean.indexing.models import ConnectorOptions
from tests.unit_tests.common.mock_clients import MockPeopleClient


class DummyPeopleConnector(BasePeopleConnector[dict]):
    configuration = MagicMock()

    def transform(self, data):
        return [
            EmployeeInfoDefinition(
                **{
                    "id": item["id"],
                    "name": item["name"],
                    "email": item["email"],
                    "manager_id": item["manager_id"],
                    "department": item["department"],
                    "title": item["title"],
                    "start_date": item["start_date"],
                    "location": item["location"],
                }
            )
            for item in data
        ]


def test_get_data_returns_all_people():
    client = MagicMock()
    client.get_source_data.return_value = MockPeopleClient().get_all_people()
    connector = DummyPeopleConnector("test_people", client)
    result = connector.get_data()
    assert len(result) == 5
    assert result[0]["id"] == "user-1"


def test_transform_maps_to_employee_info():
    connector = DummyPeopleConnector("test_people", MagicMock())
    data = MockPeopleClient().get_all_people()
    employees = connector.transform(data)
    assert all(isinstance(e, EmployeeInfoDefinition) for e in employees)
    assert employees[0].id == "user-1"


def test_index_data_batches_and_uploads():
    client = MagicMock()
    client.get_source_data.return_value = MockPeopleClient().get_all_people()
    connector = DummyPeopleConnector("test_people", client)
    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data()
        assert bulk_index.call_count == 1
        _, kwargs = bulk_index.call_args
        assert kwargs["is_first_page"] is True
        assert kwargs["is_last_page"] is True
        assert len(kwargs["employees"]) == 5


def test_index_data_empty():
    client = MagicMock()
    client.get_source_data.return_value = []
    connector = DummyPeopleConnector("test_people", client)
    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data()
        assert bulk_index.call_count == 0


def test_index_data_error_handling():
    client = MagicMock()
    client.get_source_data.return_value = MockPeopleClient().get_all_people()
    connector = DummyPeopleConnector("test_people", client)
    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        bulk_index.side_effect = Exception("upload failed")
        with pytest.raises(Exception):
            connector.index_data()


def test_force_restart_upload():
    """Test that force_restart option sets force_restart_upload on first batch."""
    client = MagicMock()
    people_data = MockPeopleClient().get_all_people()
    client.get_source_data.return_value = people_data
    connector = DummyPeopleConnector("test_people", client)
    connector.batch_size = 2

    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data(options=ConnectorOptions(force_restart=True))

        # 5 people with batch_size=2 = 3 batches
        assert bulk_index.call_count == 3

        first_call_kwargs = bulk_index.call_args_list[0][1]
        assert first_call_kwargs["force_restart_upload"] is True
        assert first_call_kwargs["is_first_page"] is True

        second_call_kwargs = bulk_index.call_args_list[1][1]
        assert second_call_kwargs["force_restart_upload"] is None
        assert second_call_kwargs["is_first_page"] is False


def test_disable_stale_deletion_check_on_last_page_only():
    """Test that disable_stale_data_deletion_check is set only on the last batch."""
    client = MagicMock()
    people_data = MockPeopleClient().get_all_people()
    client.get_source_data.return_value = people_data
    connector = DummyPeopleConnector("test_people", client)
    connector.batch_size = 2

    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data(options=ConnectorOptions(disable_stale_deletion_check=True))

        # 5 people with batch_size=2 = 3 batches
        assert bulk_index.call_count == 3

        first_call_kwargs = bulk_index.call_args_list[0][1]
        assert first_call_kwargs["disable_stale_data_deletion_check"] is None

        second_call_kwargs = bulk_index.call_args_list[1][1]
        assert second_call_kwargs["disable_stale_data_deletion_check"] is None

        last_call_kwargs = bulk_index.call_args_list[2][1]
        assert last_call_kwargs["disable_stale_data_deletion_check"] is True


def test_upload_timeout_ms_passed_to_bulk_index():
    """Test that upload_timeout_ms is forwarded to every bulk_index call."""
    client = MagicMock()
    people_data = MockPeopleClient().get_all_people()
    client.get_source_data.return_value = people_data
    connector = DummyPeopleConnector("test_people", client)
    connector.batch_size = 2

    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data(options=ConnectorOptions(upload_timeout_ms=120_000))

        # 5 people with batch_size=2 = 3 batches
        assert bulk_index.call_count == 3
        for call in bulk_index.call_args_list:
            assert call[1]["timeout_ms"] == 120_000


def test_upload_timeout_ms_defaults_to_none():
    """Test that timeout_ms is None when no options are provided (SDK default applies)."""
    client = MagicMock()
    client.get_source_data.return_value = MockPeopleClient().get_all_people()
    connector = DummyPeopleConnector("test_people", client)

    with patch("glean.indexing.connectors.base_people_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.people.bulk_index
        connector.index_data()

        assert bulk_index.call_args[1]["timeout_ms"] is None
