"""Glean connector test harness.

Provides :class:`TestHarness` and :class:`TestConfig` for progressive connector
testing across three phases (full mock → integration → end-to-end).

Typical import::

    from glean.indexing.testing.harness import TestHarness, TestConfig
"""

from glean.indexing.testing.harness.config import ClientConfig, TestConfig
from glean.indexing.testing.harness.harness import TestHarness

__all__ = ["ClientConfig", "TestConfig", "TestHarness"]
