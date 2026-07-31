"""Tests for CacheManifest serialisation, loading, and staleness."""

import json
from pathlib import Path

import pytest

from glean.indexing.testing.harness.cache.manifest import CacheManifest


class TestCacheManifestCreate:
    def test_fields_populated(self):
        m = CacheManifest.create(
            connector="my_connector",
            client="tickets",
            sdk_version="1.0.0b2",
            item_count=42,
        )
        assert m.connector == "my_connector"
        assert m.client == "tickets"
        assert m.sdk_version == "1.0.0b2"
        assert m.item_count == 42
        assert m.phase == "integration"
        assert m.schema_version == 1
        assert m.recorded_at  # non-empty ISO timestamp

    def test_recorded_at_is_utc(self):
        m = CacheManifest.create(connector="c", client="cl", sdk_version="1.0", item_count=0)
        # ISO format includes '+00:00' for UTC-aware datetime
        assert "+00:00" in m.recorded_at or "Z" in m.recorded_at or m.recorded_at.endswith("00:00")


class TestCacheManifestSaveLoad:
    def test_round_trip(self, tmp_path: Path):
        m = CacheManifest.create(
            connector="test_conn",
            client="data_client",
            sdk_version="1.2.3",
            item_count=99,
        )
        manifest_path = tmp_path / "manifest.json"
        m.save(manifest_path)

        loaded = CacheManifest.load(manifest_path)
        assert loaded.connector == "test_conn"
        assert loaded.client == "data_client"
        assert loaded.sdk_version == "1.2.3"
        assert loaded.item_count == 99
        assert loaded.version == 1

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        m = CacheManifest.create(connector="c", client="cl", sdk_version="1.0", item_count=0)
        deep = tmp_path / "a" / "b" / "c" / "manifest.json"
        m.save(deep)
        assert deep.exists()

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            CacheManifest.load(tmp_path / "missing.json")

    def test_load_ignores_unknown_keys(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "connector": "c",
                    "phase": "integration",
                    "client": "cl",
                    "sdk_version": "0.1",
                    "schema_version": 1,
                    "recorded_at": "2026-01-01T00:00:00+00:00",
                    "item_count": 5,
                    "future_field": "ignored",
                }
            )
        )
        loaded = CacheManifest.load(path)
        assert loaded.item_count == 5


class TestCacheManifestStaleness:
    def test_same_version_not_stale(self):
        m = CacheManifest(sdk_version="1.0.0b2")
        assert m.is_stale("1.0.0b2") is False

    def test_different_version_is_stale(self):
        m = CacheManifest(sdk_version="1.0.0b1")
        assert m.is_stale("1.0.0b2") is True

    def test_unknown_version_is_stale(self):
        m = CacheManifest(sdk_version="unknown")
        assert m.is_stale("1.0.0b2") is True
