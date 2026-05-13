"""Tests for the patch-target registry."""

import importlib

import pytest

from glean.indexing.testing import _patch_targets as pt_module
from glean.indexing.testing._patch_targets import _PATCH_TARGETS, validate_patch_targets


def test_patch_targets_includes_all_four_connector_modules():
    expected = {
        "glean.indexing.connectors.base_datasource_connector.api_client",
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client",
        "glean.indexing.connectors.base_async_streaming_datasource_connector.api_client",
        "glean.indexing.connectors.base_people_connector.api_client",
    }
    assert set(_PATCH_TARGETS) == expected, (
        "If you added a new connector base class, register its module in "
        "glean.indexing.testing._patch_targets._PATCH_TARGETS."
    )


def test_validate_patch_targets_succeeds_on_normal_install():
    pt_module._validated = False
    validate_patch_targets()
    assert pt_module._validated is True


def test_validate_patch_targets_is_idempotent():
    pt_module._validated = False
    validate_patch_targets()
    validate_patch_targets()
    assert pt_module._validated is True


def test_validate_patch_targets_reports_missing_attribute(monkeypatch):
    pt_module._validated = False
    module_path = "glean.indexing.connectors.base_datasource_connector"
    module = importlib.import_module(module_path)
    monkeypatch.delattr(module, "api_client", raising=True)
    with pytest.raises(RuntimeError, match="api_client.*not found"):
        validate_patch_targets()
    pt_module._validated = False
