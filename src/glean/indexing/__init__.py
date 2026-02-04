"""Glean Indexing SDK.

A Python SDK for building custom Glean indexing solutions. This package provides
the base classes and utilities to create custom connectors for Glean's indexing APIs.
"""

from importlib.metadata import PackageNotFoundError, version

from glean.indexing import models
from glean.indexing.common import BatchProcessor, ConnectorMetrics, ContentFormatter, MockGleanClient, api_client
from glean.indexing.connectors import (
    BaseAsyncStreamingDataClient,
    BaseAsyncStreamingDatasourceConnector,
    BaseConnector,
    BaseDataClient,
    BaseDatasourceConnector,
    BasePeopleConnector,
    BaseStreamingDataClient,
    BaseStreamingDatasourceConnector,
)
from glean.indexing.models import (
    DatasourceIdentityDefinitions,
    IndexingMode,
    TIndexableEntityDefinition,
    TSourceData,
)
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.testing import ConnectorTestHarness

__all__ = [
    "BaseConnector",
    "BaseDataClient",
    "BaseDatasourceConnector",
    "BasePeopleConnector",
    "BaseStreamingDataClient",
    "BaseStreamingDatasourceConnector",
    "BaseAsyncStreamingDataClient",
    "BaseAsyncStreamingDatasourceConnector",
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
    __version__ = "0.2.0"
