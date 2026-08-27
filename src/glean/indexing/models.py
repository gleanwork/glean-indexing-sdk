from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence, TypedDict, TypeVar

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    EmployeeInfoDefinition,
    UserReferenceDefinition,
)


class IndexingMode(str, Enum):
    """Specifies the indexing strategy for a datasource: full or incremental."""

    FULL = "full"
    INCREMENTAL = "incremental"


TSourceData = TypeVar("TSourceData")
"""Type variable for the raw source data type used in indexing pipelines."""

TIndexableEntityDefinition = TypeVar("TIndexableEntityDefinition")
"""Type variable for the Glean API entity definition produced by the connector (e.g., DocumentDefinition, EmployeeInfoDefinition)."""

DEFAULT_UPLOAD_MAX_WORKERS = 5


@dataclass
class ConnectorOptions:
    """Options for controlling connector indexing behavior.

    Attributes:
        force_restart: If True, discards any previous upload progress and
            starts a new upload. Sets force_restart_upload=True on the first batch.
        disable_stale_deletion_check: If True, forces synchronous deletion of
            stale documents after the upload completes. Applied only to the last batch.
            Maps to `PushUploader`'s `disable_stale_document_deletion_check` or
            `disable_stale_data_deletion_check` depending on entity type — the
            underlying Glean API names this parameter differently for documents
            vs. user/group/employee data.
        upload_timeout_ms: Per-call timeout (in milliseconds) for bulk upload
            requests. Overrides the SDK-level default for bulk_index calls only.
            Use this when uploading large batches that may exceed the default timeout.
        document_batch_size_bytes: Maximum serialized byte size for document
            bulk upload batches. Set to None to only use document count batching.
        upload_max_workers: Maximum number of concurrent middle-page bulk uploads.
            The first and last pages are always uploaded synchronously.
    """

    force_restart: bool = False
    disable_stale_deletion_check: bool = False
    upload_timeout_ms: Optional[int] = None
    document_batch_size_bytes: Optional[int] = 5 * 1024 * 1024
    upload_max_workers: int = DEFAULT_UPLOAD_MAX_WORKERS


class DatasourceIdentityDefinitions(TypedDict, total=False):
    """Defines user, group, and membership identity data for a datasource."""

    users: Sequence[Any]
    groups: Sequence[Any]
    memberships: Sequence[Any]


__all__ = [
    "ConnectorOptions",
    "CustomDatasourceConfig",
    "DocumentDefinition",
    "EmployeeInfoDefinition",
    "ContentDefinition",
    "UserReferenceDefinition",
    "IndexingMode",
    "DatasourceIdentityDefinitions",
    "TSourceData",
    "TIndexableEntityDefinition",
    "DEFAULT_UPLOAD_MAX_WORKERS",
]
