"""Shared connector fixtures for testing-helper tests."""

from typing import Sequence

from glean.api_client.models import (
    ContentDefinition,
    DocumentDefinition,
    EmployeeInfoDefinition,
)
from glean.indexing.connectors import (
    BaseAsyncStreamingDatasourceConnector,
    BaseDatasourceConnector,
    BasePeopleConnector,
    BaseStreamingDatasourceConnector,
)
from glean.indexing.models import CustomDatasourceConfig


def _doc(item: dict, datasource: str) -> DocumentDefinition:
    return DocumentDefinition(
        id=item["id"],
        datasource=datasource,
        title=item["title"],
        view_url=item.get("url", f"https://example.com/{item['id']}"),
        body=ContentDefinition(mime_type="text/plain", text_content=item.get("body", "")),
    )


class DatasourceFake(BaseDatasourceConnector[dict]):
    configuration = CustomDatasourceConfig(
        name="fake_ds",
        display_name="Fake DS",
        url_regex=r"https://example\.com/.*",
    )

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [_doc(item, self.name) for item in data]


class StreamingFake(BaseStreamingDatasourceConnector[dict]):
    configuration = CustomDatasourceConfig(
        name="fake_streaming",
        display_name="Fake Streaming",
        url_regex=r"https://example\.com/.*",
    )

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [_doc(item, self.name) for item in data]


class AsyncStreamingFake(BaseAsyncStreamingDatasourceConnector[dict]):
    configuration = CustomDatasourceConfig(
        name="fake_async",
        display_name="Fake Async",
        url_regex=r"https://example\.com/.*",
    )

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [_doc(item, self.name) for item in data]


class PeopleFake(BasePeopleConnector[dict]):
    def transform(self, data: Sequence[dict]) -> Sequence[EmployeeInfoDefinition]:
        return [
            EmployeeInfoDefinition(
                email=item["email"],
                first_name=item["first_name"],
                last_name=item["last_name"],
                department=item.get("department", "Engineering"),
            )
            for item in data
        ]
