import pytest

from glean.indexing.connectors.base_connector import BaseConnector


class DummyConnector(BaseConnector[dict, dict]):
    def get_data(self, since=None):
        return [{"id": 1}]

    def transform(self, data):
        return [{"id": d["id"]} for d in data]

    def index_data(self, mode=None):
        self._indexed = True


def test_abstract_methods_enforced():
    def instantiate_base():
        BaseConnector("test")  # type: ignore

    with pytest.raises(TypeError):
        instantiate_base()


def test_minimal_subclass_works():
    connector = DummyConnector("test")
    data = connector.get_data()
    assert data == [{"id": 1}]
    transformed = connector.transform(data)
    assert transformed == [{"id": 1}]
    connector.index_data()
    assert hasattr(connector, "_indexed")
