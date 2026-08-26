import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SELECTOR = REPOSITORY_ROOT / "scripts" / "find_previous_release_tag.py"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=environment,
    )


def git(repository: Path, *args: str) -> str:
    return run("git", *args, cwd=repository).stdout.strip()


def commit_file(repository: Path, name: str) -> None:
    (repository / name).write_text(f"{name}\n", encoding="utf-8")
    git(repository, "add", name)
    git(repository, "commit", "--quiet", "-m", name)


def tag(repository: Path, name: str) -> None:
    git(repository, "tag", "-a", name, "-m", name)


def invoke_selector(repository: Path, current_tag: str) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(SELECTOR),
        "--current-tag",
        current_tag,
        cwd=repository,
        check=False,
    )


@pytest.fixture
def release_history(tmp_path: Path) -> Path:
    repository = tmp_path / "history"
    repository.mkdir()
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "Release Test")
    git(repository, "config", "user.email", "release@example.com")

    commit_file(repository, "release-1.2.2")
    tag(repository, "v1.2.2")
    commit_file(repository, "malformed-nearer-tag")
    tag(repository, "v1.2.3-not-a-release")
    commit_file(repository, "release-1.2.4")
    tag(repository, "v1.2.4")
    return repository


def test_selects_nearest_strict_release_tag_and_excludes_malformed_nearer_tag(
    release_history: Path,
) -> None:
    result = invoke_selector(release_history, "v1.2.4")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v1.2.2"


@pytest.mark.parametrize("current_tag", ["1.2.4", "v1.2", "v1.2.4-extra", "vv1.2.4"])
def test_rejects_current_tag_outside_publish_grammar(
    release_history: Path, current_tag: str
) -> None:
    result = invoke_selector(release_history, current_tag)

    assert result.returncode == 1
    assert "must exactly match v<version>" in result.stderr
