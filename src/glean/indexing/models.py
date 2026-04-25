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


@dataclass
class ConnectorOptions:
    """Options for controlling connector indexing behavior.

    Attributes:
        force_restart: If True, discards any previous upload progress and
            starts a new upload. Sets force_restart_upload=True on the first batch.
        disable_stale_deletion_check: If True, forces synchronous deletion of
            stale documents after the upload completes. Applied only to the last batch.
        upload_timeout_ms: Per-call timeout (in milliseconds) for bulk upload
            requests. Overrides the SDK-level default for bulk_index calls only.
            Use this when uploading large batches that may exceed the default timeout.
    """

    force_restart: bool = False
    disable_stale_deletion_check: bool = False
    upload_timeout_ms: Optional[int] = None


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
]
