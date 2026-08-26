"""Base connector class for the Glean Connector SDK."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Literal, Optional, Sequence

from glean.indexing.common.batch_processor import DEFAULT_DOCUMENT_BATCH_SIZE_BYTES
from glean.indexing.models import (
    DEFAULT_UPLOAD_MAX_WORKERS,
    ConnectorOptions,
    IndexingMode,
    TIndexableEntityDefinition,
    TSourceData,
)
from glean.indexing.observability import ConnectorObservability
from glean.indexing.push import PushUploader

logger = logging.getLogger(__name__)

BulkUploadEntity = Literal["documents", "users", "groups", "memberships", "employees"]

_BULK_UPLOAD_OPTION_MATRIX: dict[BulkUploadEntity, tuple[str, ...]] = {
    "documents": (
        "force_restart_upload",
        "disable_stale_document_deletion_check",
        "max_batch_bytes",
    ),
    "users": ("force_restart_upload", "disable_stale_data_deletion_check"),
    "groups": ("force_restart_upload", "disable_stale_data_deletion_check"),
    "memberships": ("force_restart_upload",),
    "employees": ("force_restart_upload", "disable_stale_data_deletion_check"),
}


class BaseConnector(ABC, Generic[TSourceData, TIndexableEntityDefinition]):
    """
    Abstract base class for all Glean connectors.

    This class defines the core interface and lifecycle for all connector types (datasource, people, streaming, etc.).
    Connector implementors should inherit from this class and provide concrete implementations for all abstract methods.

    Type Parameters:
        TSourceData: The type of raw data fetched from the external source (e.g., dict, TypedDict, or custom model).
        TIndexableEntityDefinition: The type of Glean API entity definition produced by the connector (e.g., DocumentDefinition, EmployeeInfoDefinition).

    Required Methods for Subclasses:
        - get_data(since: Optional[str] = None) -> Sequence[TSourceData]:
            Fetches source data from the external system. Should support incremental fetches if possible.
        - transform(data: Sequence[TSourceData]) -> List[TIndexableEntityDefinition]:
            Transforms source data into Glean API entity definitions ready for indexing.
        - index_data(mode: IndexingMode = IndexingMode.FULL) -> None:
            Orchestrates the full indexing process (fetch, transform, upload).

    Attributes:
        name (str): The unique name of the connector (should be snake_case).

    Example:
        class MyConnector(BaseConnector[MyRawType, DocumentDefinition]):
            ...
    """

    _observability: ConnectorObservability

    def __init__(self, name: str):
        """Initialize the connector.

        Args:
            name: The name of the connector.
        """
        self.name = name

    def _create_uploader(self, options: Optional[ConnectorOptions]) -> PushUploader:
        """Create an uploader with the options shared by every bulk endpoint."""
        return PushUploader(
            datasource=self.name,
            timeout_ms=options.upload_timeout_ms if options else None,
            observability=self._observability,
            upload_max_workers=options.upload_max_workers
            if options
            else DEFAULT_UPLOAD_MAX_WORKERS,
        )

    def _bulk_upload_options(
        self, options: Optional[ConnectorOptions], entity: BulkUploadEntity
    ) -> dict[str, Any]:
        """Resolve the supported high-level options for one bulk endpoint."""
        resolved_options: dict[str, Any] = {
            "force_restart_upload": True if (options and options.force_restart) else None,
            "disable_stale_document_deletion_check": True
            if (options and options.disable_stale_deletion_check)
            else None,
            "disable_stale_data_deletion_check": True
            if (options and options.disable_stale_deletion_check)
            else None,
        }
        if entity == "documents":
            resolved_options["max_batch_bytes"] = self._resolve_max_batch_bytes(options)
        return {
            option_name: resolved_options[option_name]
            for option_name in _BULK_UPLOAD_OPTION_MATRIX[entity]
        }

    @staticmethod
    def _resolve_max_batch_bytes(options: Optional[ConnectorOptions]) -> Optional[int]:
        """Resolve the document byte limit, allowing datasource connectors to override it."""
        return options.document_batch_size_bytes if options else DEFAULT_DOCUMENT_BATCH_SIZE_BYTES

    @abstractmethod
    def get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """Get data from the data client or source system."""
        pass

    @abstractmethod
    def transform(self, data: Sequence[TSourceData]) -> Sequence[TIndexableEntityDefinition]:
        """Transform source data to Glean entity definitions."""
        pass

    @abstractmethod
    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Index data from the connector to Glean.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            options: Optional connector options for controlling indexing behavior.
        """
        pass
