from enum import Enum
from typing import Any, Sequence, TypedDict, TypeVar

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    EmployeeInfoDefinition,
)

# --- Types moved from glean.indexing.utils.models ---


class ConnectorType(str, Enum):
    DATASOURCE = "datasource"
    PEOPLE = "people"
    STREAMING_DATASOURCE = "streaming_datasource"


class IndexingMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


TSourceData = TypeVar("TSourceData")
TGleanModel = TypeVar("TGleanModel")


class DatasourceIdentityDefinitions(TypedDict, total=False):
    users: Sequence[Any]
    groups: Sequence[Any]
    memberships: Sequence[Any]


# --- End moved types ---

__all__ = [
    "CustomDatasourceConfig",
    "DocumentDefinition",
    "EmployeeInfoDefinition",
    "ContentDefinition",
    "ConnectorType",
    "IndexingMode",
    "DatasourceIdentityDefinitions",
    "TSourceData",
    "TGleanModel",
]
