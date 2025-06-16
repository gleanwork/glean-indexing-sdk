import pytest

from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient


class DummyDataClient(BaseDataClient[dict]):
    def get_source_data(self, **kwargs):
        return [{"id": 1}]


class DummyStreamingDataClient(BaseStreamingDataClient[dict]):
    def get_source_data(self, **kwargs):
        yield {"id": 1}


def test_base_data_client_abstract():
    def instantiate_base():
        BaseDataClient()  # type: ignore

    with pytest.raises(TypeError):
        instantiate_base()


def test_base_streaming_data_client_abstract():
    def instantiate_base():
        BaseStreamingDataClient()  # type: ignore

    with pytest.raises(TypeError):
        instantiate_base()


def test_dummy_data_client():
    client = DummyDataClient()
    data = client.get_source_data()
    assert data == [{"id": 1}]


def test_dummy_streaming_data_client():
    client = DummyStreamingDataClient()
    data = list(client.get_source_data())
    assert data == [{"id": 1}]
