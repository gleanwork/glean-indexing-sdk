"""Glean Indexing SDK.

A Python SDK for building custom Glean indexing solutions. This package provides 
the base classes and utilities to create custom connectors for Glean's indexing APIs.
"""

from importlib.metadata import version, PackageNotFoundError
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.connectors.base_streaming_datasource_connector import BaseStreamingDatasourceConnector
from glean.indexing.connectors.base_people_connector import BasePeopleConnector
from glean.indexing.connectors.base_data_client import BaseConnectorDataClient
from glean.indexing.connectors.base_streaming_data_client import StreamingConnectorDataClient
from glean.indexing.clients.glean_client import api_client
from glean.indexing.clients.mocks import MockGleanClient
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.testing import ConnectorTestHarness
from glean.indexing.utils import BatchProcessor, ContentFormatter, ConnectorMetrics
from glean.indexing.models import (
    DatasourceIdentityDefinitions,
    IndexingMode,
    TSourceData,
    TIndexableEntityDefinition,
)
from glean.indexing import models

__all__ = [
    "BaseConnector",
    "BaseDatasourceConnector",
    "BasePeopleConnector",
    "BaseStreamingDatasourceConnector",
    
    "BaseConnectorDataClient",
    "StreamingConnectorDataClient",
    
    "BatchProcessor",
    "ContentFormatter",
    "ConnectorMetrics",
    "ConnectorObservability",
    "ConnectorTestHarness",
    
    "DatasourceIdentityDefinitions",
    "IndexingMode",
    "TSourceData",
    "TIndexableEntityDefinition",
    
    "MockGleanClient",
    "api_client",

    "models",
]

try:
    __version__ = version("glean-indexing-sdk")
except PackageNotFoundError:
    __version__ = "0.0.1"