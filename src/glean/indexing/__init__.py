"""Glean Indexing SDK.

A Python SDK for building custom Glean indexing solutions. This package provides
the base classes and utilities to create custom connectors for Glean's indexing APIs.
"""

from importlib.metadata import PackageNotFoundError, version

from glean.indexing import models
from glean.indexing.exceptions import (
    GleanConfigurationError,
    GleanError,
    GleanValidationError,
    InconsistentDataError,
    InvalidDatasourceConfigError,
    InvalidPropertyError,
    MissingEnvironmentVariableError,
    UnsupportedConnectorTypeError,
)
from glean.indexing.common import BatchProcessor, ConnectorMetrics, ContentFormatter, api_client
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
    ConnectorOptions,
    DatasourceIdentityDefinitions,
    IndexingMode,
    TIndexableEntityDefinition,
    TSourceData,
)
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.push import PushUploader
from glean.indexing.testing import (
    MockGleanClient,
    StaticAsyncStreamingDataClient,
    StaticDataClient,
    StaticStreamingDataClient,
    mock_glean_client,
    run_connector,
    run_connector_async,
    with_mock_glean_client,
)

__all__ = [
    "BaseConnector",
    "ConnectorOptions",
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
    "PushUploader",
    "DatasourceIdentityDefinitions",
    "IndexingMode",
    "TSourceData",
    "TIndexableEntityDefinition",
    "MockGleanClient",
    "StaticAsyncStreamingDataClient",
    "StaticDataClient",
    "StaticStreamingDataClient",
    "api_client",
    "mock_glean_client",
    "run_connector",
    "run_connector_async",
    "with_mock_glean_client",
    "models",
    "GleanError",
    "GleanConfigurationError",
    "GleanValidationError",
    "MissingEnvironmentVariableError",
    "InvalidDatasourceConfigError",
    "InvalidPropertyError",
    "InconsistentDataError",
    "UnsupportedConnectorTypeError",
]

try:
    __version__ = version("glean-indexing-sdk")
except PackageNotFoundError:
    __version__ = "1.0.0b2"
