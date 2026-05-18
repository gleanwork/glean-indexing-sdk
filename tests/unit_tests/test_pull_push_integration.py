"""Pull + push smoke tests."""

from typing import Sequence

from glean.api_client.models import ContentDefinition, DocumentDefinition
from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from glean.indexing.models import CustomDatasourceConfig
from glean.indexing.pull import BearerTokenAuth, PullHttpClient, PullOptions, PullRetryOptions
from glean.indexing.testing import run_connector


class HttpBackedDataClient(BaseDataClient[dict]):
    """Tiny source data client that uses the pull layer."""

    def __init__(self, client: PullHttpClient):
        self.client = client

    def get_source_data(self, since=None) -> Sequence[dict]:
        response = self.client.get("/records")
        return response.json_dict()["items"]


class PullPushConnector(BaseDatasourceConnector[dict]):
    """Connector used to verify pull records flow into push uploads."""

    configuration = CustomDatasourceConfig(
        name="pull_push",
        display_name="Pull Push",
        url_regex=r"https://example\.com/.*",
    )

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=item["id"],
                title=item["title"],
                datasource=self.name,
                view_url=f"https://example.com/{item['id']}",
                body=ContentDefinition(mime_type="text/plain", text_content=item["body"]),
            )
            for item in data
        ]


def test_pull_http_records_can_be_pushed_through_connector(httpx_mock):
    httpx_mock.add_response(
        url="https://source.example.com/api/records",
        json={
            "items": [
                {"id": "1", "title": "First", "body": "hello"},
                {"id": "2", "title": "Second", "body": "world"},
            ]
        },
        headers={"Content-Type": "application/json"},
    )
    pull_client = PullHttpClient(
        base_url="https://source.example.com/api",
        auth=BearerTokenAuth("source-token"),
        options=PullOptions(
            retries=PullRetryOptions(
                initial_backoff_seconds=0,
                max_backoff_seconds=0,
            )
        ),
    )
    connector = PullPushConnector("pull_push", HttpBackedDataClient(pull_client))

    result = run_connector(connector)

    result.assert_documents_posted(count=2, datasource="pull_push")
    assert [doc.id for doc in result.documents_posted] == ["1", "2"]
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer source-token"
