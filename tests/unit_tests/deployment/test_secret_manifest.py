"""Tests for the local connector secret-key manifest."""

import os
from pathlib import Path

import pytest

from glean.indexing.deployment import secret_manifest
from glean.indexing.deployment.secret_manifest import (
    env_keys_from_upload_results,
    read_manifest,
    write_manifest,
)


def test_upload_result_mapping_returns_sorted_unique_environment_keys() -> None:
    prefix = "CUSTOM_DATASOURCE_PLATFORM_MY_CONNECTOR_"
    results = {
        f"{prefix}Z_KEY": "created",
        f"{prefix}A_KEY": "updated",
    }

    assert env_keys_from_upload_results(results, prefix) == ["A_KEY", "Z_KEY"]


@pytest.mark.parametrize(
    "results",
    [
        {"CUSTOM_DATASOURCE_PLATFORM_OTHER_API_KEY": "created"},
        {"CUSTOM_DATASOURCE_PLATFORM_MY_CONNECTOR_BAD.KEY": "created"},
    ],
)
def test_upload_result_mapping_rejects_wrong_prefix_or_malformed_key(
    results: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        env_keys_from_upload_results(results, "CUSTOM_DATASOURCE_PLATFORM_MY_CONNECTOR_")


def test_manifest_read_rejects_malformed_environment_key(tmp_path: Path) -> None:
    path = tmp_path / ".glean_secret_keys"
    path.write_text("VALID_KEY\nBAD.KEY\n")

    with pytest.raises(ValueError, match="Environment variable key"):
        read_manifest(path)


def test_manifest_missing_and_empty_are_secretless(tmp_path: Path) -> None:
    path = tmp_path / ".glean_secret_keys"

    assert read_manifest(path) == []

    path.write_text("STALE_KEY\n")
    write_manifest(path, [])

    assert path.exists()
    assert path.read_bytes() == b""
    assert read_manifest(path) == []


def test_manifest_write_is_sorted_validated_and_atomically_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".glean_secret_keys"
    path.write_text("OLD_KEY\n")
    real_replace = os.replace
    replacements: list[tuple[Path, Path]] = []

    def record_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        replacements.append((Path(source), Path(destination)))
        assert path.read_text() == "OLD_KEY\n"
        real_replace(source, destination)

    monkeypatch.setattr(secret_manifest.os, "replace", record_replace)

    write_manifest(path, ["Z_KEY", "A_KEY", "Z_KEY"])

    assert path.read_text() == "A_KEY\nZ_KEY\n"
    assert len(replacements) == 1
    temporary, destination = replacements[0]
    assert destination == path
    assert temporary.parent == path.parent
    assert not temporary.exists()


def test_manifest_write_validates_all_keys_before_replacing(tmp_path: Path) -> None:
    path = tmp_path / ".glean_secret_keys"
    path.write_text("OLD_KEY\n")

    with pytest.raises(ValueError, match="Environment variable key"):
        write_manifest(path, ["VALID_KEY", "BAD.KEY"])

    assert path.read_text() == "OLD_KEY\n"
