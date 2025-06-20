"""Glean Indexing SDK.

A Python SDK for building custom Glean indexing solutions. This package provides 
the base classes and utilities to create custom connectors for Glean's indexing APIs.
"""

from importlib.metadata import version, PackageNotFoundError
from glean.indexing.connectors import (
    BaseConnector,
    BaseDatasourceConnector,
    BaseStreamingDatasourceConnector,
    BasePeopleConnector,
    BaseConnectorDataClient,
    StreamingConnectorDataClient,
)
from glean.indexing.common import BatchProcessor, ContentFormatter, ConnectorMetrics, api_client, MockGleanClient
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.testing import ConnectorTestHarness
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
    __version__ = "0.0.2"