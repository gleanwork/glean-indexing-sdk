"""Glean connector test harness.

Provides :class:`TestHarness` and :class:`TestConfig` for progressive connector
testing across three phases (full mock → integration → end-to-end).

Typical import::

    from glean.indexing.testing.harness import TestHarness, TestConfig
"""

from glean.indexing.testing.harness.config import ClientConfig, TestConfig
from glean.indexing.testing.harness.harness import TestHarness
from glean.indexing.testing.harness.indexing_wait import IndexingWaitResult
from glean.indexing.testing.harness.permissions import (
    PermissionRefs,
    assert_negative_identities_absent,
    extract_permission_refs,
)

__all__ = [
    "ClientConfig",
    "IndexingWaitResult",
    "PermissionRefs",
    "TestConfig",
    "TestHarness",
    "assert_negative_identities_absent",
    "extract_permission_refs",
]
