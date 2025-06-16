from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import EmployeeInfoDefinition
from glean.indexing.connectors.base_people_connector import BasePeopleConnector
from tests.unit_tests.utils.mock_clients import MockPeopleClient


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
