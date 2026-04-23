from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence, TypedDict, TypeVar

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
    """Options for controlling connector indexing behavior."""

    force_restart: bool = False
    disable_stale_deletion_check: bool = False


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
