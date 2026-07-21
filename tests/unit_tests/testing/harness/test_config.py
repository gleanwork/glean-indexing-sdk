"""Tests for TestConfig and ClientConfig."""

import textwrap
from pathlib import Path

import pytest

from glean.indexing.testing.harness.config import ClientConfig, TestConfig


class TestClientConfig:
    def test_defaults(self):
        cfg = ClientConfig()
        assert cfg.max_items == 5

    def test_from_dict_full(self):
        cfg = ClientConfig.from_dict({"max_items": 100})
        assert cfg.max_items == 100

    def test_from_dict_empty(self):
        cfg = ClientConfig.from_dict({})
        assert cfg.max_items == 5

    def test_explicit_none_disables_limit(self):
        cfg = ClientConfig.from_dict({"max_items": None})
        assert cfg.max_items is None


class TestTestConfigDefaults:
    def test_defaults(self):
        cfg = TestConfig()
        assert cfg.cache_dir == ".glean_test_cache/"
        assert cfg.use_cache is True
        assert cfg.refresh_cache is False
        assert cfg.run_id_prefix == "sdk_test"
        assert cfg.initial_index_wait_seconds == 45
        assert cfg.index_poll_interval_seconds == 30
        assert cfg.index_wait_timeout_seconds == 300
        assert cfg.clients == {}
        assert cfg.negative_test_identities == []


class TestTestConfigFromDict:
    def test_full(self):
        data = {
            "cache_dir": "/tmp/cache/",
            "use_cache": False,
            "refresh_cache": True,
            "run_id_prefix": "my_test",
            "initial_index_wait_seconds": 35,
            "index_poll_interval_seconds": 10,
            "index_wait_timeout_seconds": 120,
            "clients": {
                "tickets": {"max_items": 50},
                "comments": {"max_items": 200},
            },
            "negative_test_identities": ["denied@example.com", "bad_group"],
        }
        cfg = TestConfig.from_dict(data)

        assert cfg.cache_dir == "/tmp/cache/"
        assert cfg.use_cache is False
        assert cfg.refresh_cache is True
        assert cfg.run_id_prefix == "my_test"
        assert cfg.initial_index_wait_seconds == 35
        assert cfg.index_poll_interval_seconds == 10
        assert cfg.index_wait_timeout_seconds == 120
        assert cfg.clients["tickets"].max_items == 50
        assert cfg.clients["comments"].max_items == 200
        assert cfg.negative_test_identities == ["denied@example.com", "bad_group"]

    def test_minimal(self):
        cfg = TestConfig.from_dict({})
        assert cfg.cache_dir == ".glean_test_cache/"
        assert cfg.clients == {}
        assert cfg.negative_test_identities == []

    def test_clients_none_value(self):
        # YAML can emit null for an empty mapping
        cfg = TestConfig.from_dict({"clients": None})
        assert cfg.clients == {}

    def test_negative_identities_none(self):
        cfg = TestConfig.from_dict({"negative_test_identities": None})
        assert cfg.negative_test_identities == []


class TestTestConfigFromYaml:
    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "testing_config.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_complete_yaml(self, tmp_path: Path):
        yaml_path = self._write_yaml(
            tmp_path,
            """\
            testing:
              cache_dir: .cache/
              use_cache: true
              refresh_cache: false
              run_id_prefix: ci_test
              clients:
                tickets:
                  max_items: 500
                users:
                  max_items: 50
              negative_test_identities:
                - "test_denied@example.com"
            """,
        )
        cfg = TestConfig.from_yaml(yaml_path)

        assert cfg.cache_dir == ".cache/"
        assert cfg.use_cache is True
        assert cfg.refresh_cache is False
        assert cfg.run_id_prefix == "ci_test"
        assert cfg.clients["tickets"].max_items == 500
        assert cfg.clients["users"].max_items == 50
        assert cfg.negative_test_identities == ["test_denied@example.com"]

    def test_minimal_yaml(self, tmp_path: Path):
        yaml_path = self._write_yaml(
            tmp_path,
            """\
            testing: {}
            """,
        )
        cfg = TestConfig.from_yaml(yaml_path)

        assert cfg.cache_dir == ".glean_test_cache/"
        assert cfg.use_cache is True
        assert cfg.negative_test_identities == []

    def test_file_not_found(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError, match="does_not_exist.yaml"):
            TestConfig.from_yaml(missing)

    def test_missing_testing_key(self, tmp_path: Path):
        yaml_path = self._write_yaml(
            tmp_path,
            """\
            other_key:
              foo: bar
            """,
        )
        with pytest.raises(KeyError, match="testing"):
            TestConfig.from_yaml(yaml_path)

    def test_path_as_string(self, tmp_path: Path):
        yaml_path = self._write_yaml(
            tmp_path,
            """\
            testing:
              run_id_prefix: string_path_test
            """,
        )
        # Pass path as str, not Path
        cfg = TestConfig.from_yaml(str(yaml_path))
        assert cfg.run_id_prefix == "string_path_test"

    def test_negative_test_identities_parsed(self, tmp_path: Path):
        yaml_path = self._write_yaml(
            tmp_path,
            """\
            testing:
              negative_test_identities:
                - "user_a@corp.com"
                - "group_b"
                - "user_c@corp.com"
            """,
        )
        cfg = TestConfig.from_yaml(yaml_path)
        assert len(cfg.negative_test_identities) == 3
        assert "group_b" in cfg.negative_test_identities
