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


class DatasourceIdentityDefinitions(TypedDict, total=False):
    """Defines user, group, and membership identity data for a datasource."""

    users: Sequence[Any]
    groups: Sequence[Any]
    memberships: Sequence[Any]


__all__ = [
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
