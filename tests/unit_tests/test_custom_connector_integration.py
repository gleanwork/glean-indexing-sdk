from unittest.mock import patch

import pytest

from glean.api_client.models.contentdefinition import ContentDefinition
from glean.api_client.models.customdatasourceconfig import (
    CustomDatasourceConfig,
    CustomDatasourceConfigConnectorType,
    DatasourceCategory,
)
from glean.api_client.models.documentdefinition import DocumentDefinition
from glean.api_client.models.userreferencedefinition import UserReferenceDefinition
from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from tests.unit_tests.utils.mock_clients import MockDataSourceClient


class CustomDatasourceConnector(BaseDatasourceConnector[dict]):
    configuration = CustomDatasourceConfig(
        name="custom_ds",
        display_name="Custom Datasource",
        datasource_category=DatasourceCategory.UNCATEGORIZED,
        connector_type=CustomDatasourceConfigConnectorType.API_CRAWL,
    )

    def transform(self, data):
        return [
            DocumentDefinition(
                datasource="custom_ds",
                id=item["id"],
                title=item["title"],
                body=ContentDefinition(mime_type="text/plain", text_content=item["content"]),
                view_url=item["url"],
                created_at=1672531200,
                updated_at=1672617600,
                author=UserReferenceDefinition(email=item["author"]),
                tags=item["tags"],
            )
            for item in data
        ]


class MockClient(BaseDataClient[dict]):
    def __init__(self, items):
        self._items = items

    def get_source_data(self, since=None):
        return self._items


def test_custom_datasource_connector_index_data():
    items = MockDataSourceClient().get_all_items()
    connector = CustomDatasourceConnector("custom_ds", MockClient(items))

    with patch("glean.indexing.connectors.base_datasource_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()

        assert bulk_index.call_count == 1
        _, kwargs = bulk_index.call_args

        assert kwargs["datasource"] == "custom_ds"
        assert len(kwargs["documents"]) == 5


def test_custom_datasource_connector_empty_data():
    connector = CustomDatasourceConnector("custom_ds", MockClient([]))

    with patch("glean.indexing.connectors.base_datasource_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()

        assert bulk_index.call_count == 0


def test_custom_datasource_connector_api_error():
    items = MockDataSourceClient().get_all_items()
    connector = CustomDatasourceConnector("custom_ds", MockClient(items))

    with patch("glean.indexing.connectors.base_datasource_connector.api_client") as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        bulk_index.side_effect = Exception("upload failed")

        with pytest.raises(Exception):
            connector.index_data()
