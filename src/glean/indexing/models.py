from enum import Enum
from typing import Any, Sequence, TypedDict, TypeVar

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    EmployeeInfoDefinition,
)


class IndexingMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


TSourceData = TypeVar("TSourceData")
TGleanModel = TypeVar("TGleanModel")


class DatasourceIdentityDefinitions(TypedDict, total=False):
    users: Sequence[Any]
    groups: Sequence[Any]
    memberships: Sequence[Any]


__all__ = [
    "CustomDatasourceConfig",
    "DocumentDefinition",
    "EmployeeInfoDefinition",
    "ContentDefinition",
    "IndexingMode",
    "DatasourceIdentityDefinitions",
    "TSourceData",
    "TGleanModel",
]
