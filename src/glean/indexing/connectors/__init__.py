"""Connector implementations for Glean indexing."""

from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient, BaseConnectorDataClient
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.connectors.base_people_connector import BasePeopleConnector
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient, StreamingConnectorDataClient
from glean.indexing.connectors.base_streaming_datasource_connector import BaseStreamingDatasourceConnector
from glean.indexing.connectors.async_streaming import (
    AsyncBaseStreamingDataClient,
    AsyncBaseStreamingDatasourceConnector,
    AsyncStreamingDataClient,
    AsyncStreamingDatasourceConnector,
)
from glean.indexing.testing.connector_test_harness import ConnectorTestHarness

__all__ = [
    "BaseConnector",
    "BaseDataClient",
    "BaseConnectorDataClient",  # Backward compatibility alias
    "BaseDatasourceConnector",
    "BasePeopleConnector",
    "BaseStreamingDataClient",
    "StreamingConnectorDataClient",  # Backward compatibility alias
    "BaseStreamingDatasourceConnector",
    # Async streaming classes
    "AsyncBaseStreamingDataClient",
    "AsyncBaseStreamingDatasourceConnector",
    "AsyncStreamingDataClient",  # Convenience alias
    "AsyncStreamingDatasourceConnector",  # Convenience alias
    "ConnectorTestHarness",
]
