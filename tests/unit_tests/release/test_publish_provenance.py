import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GUARD = REPOSITORY_ROOT / "scripts" / "check_publish_provenance.py"
PROJECT_NAME = "glean-indexing-sdk"
PROJECT_URLS = {
    "Source Code": "https://github.com/gleanwork/glean-indexing-sdk",
    "Issues": "https://github.com/gleanwork/glean-indexing-sdk/issues",
    "Documentation": "https://developers.glean.com/libraries/indexing-sdk",
}


def artifact_metadata(
    version: str,
    *,
    project_urls: dict[str, str] = PROJECT_URLS,
    description: str = "[![GA](https://img.shields.io/badge/-GA)]\n",
) -> str:
    url_headers = "".join(f"Project-URL: {label}, {url}\n" for label, url in project_urls.items())
    return (
        f"Metadata-Version: 2.4\n"
        f"Name: {PROJECT_NAME}\n"
        f"Version: {version}\n"
        f"{url_headers}\n"
        f"{description}"
    )


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


def write_sources(repository: Path, version: str = "1.2.3") -> None:
    (repository / "src/glean/indexing").mkdir(parents=True)
    (repository / "pyproject.toml").write_text(
        f'[project]\nname = "{PROJECT_NAME}"\nversion = "{version}"\n', encoding="utf-8"
    )
    (repository / ".cz.toml").write_text(
        f'[tool.commitizen]\nversion = "{version}"\n', encoding="utf-8"
    )
    (repository / "src/glean/indexing/__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )


def write_artifacts(repository: Path, version: str = "1.2.3") -> Path:
    dist = repository / "dist"
    dist.mkdir()
    metadata = artifact_metadata(version)
    wheel = dist / f"glean_indexing_sdk-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"glean_indexing_sdk-{version}.dist-info/METADATA", metadata)
    sdist = dist / f"glean_indexing_sdk-{version}.tar.gz"
    pkg_info = repository / "PKG-INFO"
    pkg_info.write_text(metadata, encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname=f"glean_indexing_sdk-{version}/PKG-INFO")
    pkg_info.unlink()
    return dist


def rewrite_artifact_metadata(
    repository: Path,
    dist: Path,
    artifact: str,
    metadata: str,
    *,
    filename_version: str = "1.2.3",
) -> None:
    if artifact == "wheel":
        wheel = dist / f"glean_indexing_sdk-{filename_version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(f"glean_indexing_sdk-{filename_version}.dist-info/METADATA", metadata)
        return

    sdist = dist / f"glean_indexing_sdk-{filename_version}.tar.gz"
    pkg_info = repository / "PKG-INFO"
    pkg_info.write_text(metadata, encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname=f"glean_indexing_sdk-{filename_version}/PKG-INFO")
    pkg_info.unlink()


@pytest.fixture
def release_repository(tmp_path: Path) -> tuple[Path, Path, str]:
    repository = tmp_path / "release"
    repository.mkdir()
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "Release Test")
    git(repository, "config", "user.email", "release@example.com")
    write_sources(repository)
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "release")
    git(repository, "tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
    return repository, write_artifacts(repository), git(repository, "rev-parse", "HEAD")


def invoke_guard(
    repository: Path,
    dist: Path,
    head: str,
    *,
    tag: str = "v1.2.3",
    manifest_option: tuple[str, Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(GUARD),
        "--tag",
        tag,
        "--sha",
        head,
        "--dist",
        str(dist),
    ]
    if manifest_option:
        arguments.extend((manifest_option[0], str(manifest_option[1])))
    return run(*arguments, cwd=repository, check=False)


def assert_rejected(result: subprocess.CompletedProcess[str], message: str) -> None:
    assert result.returncode == 1
    assert message in result.stderr


def retag_head(repository: Path, tag: str = "v1.2.3") -> str:
    git(repository, "tag", "--delete", tag)
    git(repository, "tag", "-a", tag, "-m", f"Release {tag}")
    return git(repository, "rev-parse", "HEAD")


def test_accepts_tagged_sources_and_artifacts_and_writes_sha_bound_manifest(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, head = release_repository
    manifest = repository / "release-provenance.json"

    result = invoke_guard(repository, dist, head, manifest_option=("--write-manifest", manifest))

    assert result.returncode == 0, result.stderr

    assert result.stdout.strip() == f"Verified {PROJECT_NAME} 1.2.3 at v1.2.3 ({head})."
    provenance = json.loads(manifest.read_text(encoding="utf-8"))
    assert provenance == {
        "artifacts": {
            "glean_indexing_sdk-1.2.3-py3-none-any.whl": hashlib.sha256(
                (dist / "glean_indexing_sdk-1.2.3-py3-none-any.whl").read_bytes()
            ).hexdigest(),
            "glean_indexing_sdk-1.2.3.tar.gz": hashlib.sha256(
                (dist / "glean_indexing_sdk-1.2.3.tar.gz").read_bytes()
            ).hexdigest(),
        },
        "commit": head,
        "project": PROJECT_NAME,
        "tag": "v1.2.3",
        "version": "1.2.3",
    }


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2", "v1.2.3.4", "vv1.2.3", "v1.2.3-beta.1"])
def test_rejects_non_exact_release_tags(
    release_repository: tuple[Path, Path, str], tag: str
) -> None:
    repository, dist, head = release_repository

    assert_rejected(invoke_guard(repository, dist, head, tag=tag), "Release tag must exactly match")


def test_rejects_event_sha_that_is_not_checked_out(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, _ = release_repository

    assert_rejected(invoke_guard(repository, dist, "0" * 40), "does not match release commit")


def test_rejects_tag_that_does_not_point_to_head(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, _ = release_repository
    (repository / "after-tag").write_text("later\n", encoding="utf-8")
    git(repository, "add", "after-tag")
    git(repository, "commit", "--quiet", "-m", "later")
    head = git(repository, "rev-parse", "HEAD")

    assert_rejected(invoke_guard(repository, dist, head), "not release commit")


def test_rejects_divergent_sdk_version_sources(release_repository: tuple[Path, Path, str]) -> None:
    repository, dist, _ = release_repository
    module = repository / "src/glean/indexing/__init__.py"
    module.write_text('__version__ = "1.2.4"\n', encoding="utf-8")
    git(repository, "add", str(module))
    git(repository, "commit", "--quiet", "-m", "diverge version")
    head = retag_head(repository)

    assert_rejected(invoke_guard(repository, dist, head), "SDK version sources differ")


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_rejects_artifact_metadata_version_mismatch(
    release_repository: tuple[Path, Path, str], artifact: str
) -> None:
    repository, dist, head = release_repository
    rewrite_artifact_metadata(repository, dist, artifact, artifact_metadata("1.2.4"))

    assert_rejected(invoke_guard(repository, dist, head), "expected glean-indexing-sdk 1.2.3")


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_rejects_artifact_with_noncanonical_project_url(
    release_repository: tuple[Path, Path, str], artifact: str
) -> None:
    repository, dist, head = release_repository
    project_urls = {
        **PROJECT_URLS,
        "Source Code": "https://github.com/glean-io/glean-indexing-sdk",
    }
    rewrite_artifact_metadata(
        repository,
        dist,
        artifact,
        artifact_metadata("1.2.3", project_urls=project_urls),
    )

    assert_rejected(
        invoke_guard(repository, dist, head),
        "Project-URL 'Source Code' is 'https://github.com/glean-io/glean-indexing-sdk'",
    )


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_rejects_prerelease_badge_in_ga_long_description(
    release_repository: tuple[Path, Path, str], artifact: str
) -> None:
    repository, dist, head = release_repository
    rewrite_artifact_metadata(
        repository,
        dist,
        artifact,
        artifact_metadata(
            "1.2.3",
            description="[![Prerelease](https://img.shields.io/badge/-Prerelease)]\n",
        ),
    )

    assert_rejected(
        invoke_guard(repository, dist, head),
        "long description must contain the GA badge and must not contain the Prerelease badge",
    )


def test_rejects_extra_or_missing_distribution_files(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, head = release_repository
    (dist / "unexpected.txt").write_text("not publishable\n", encoding="utf-8")

    assert_rejected(invoke_guard(repository, dist, head), "exactly one wheel and one .tar.gz sdist")


def test_rejects_artifacts_changed_after_manifest_was_written(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, head = release_repository
    manifest = repository / "release-provenance.json"
    created = invoke_guard(repository, dist, head, manifest_option=("--write-manifest", manifest))
    assert created.returncode == 0, created.stderr
    wheel = dist / "glean_indexing_sdk-1.2.3-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"changed after verification")

    assert_rejected(
        invoke_guard(repository, dist, head, manifest_option=("--verify-manifest", manifest)),
        "Transferred artifact provenance does not match",
    )


def test_rejects_source_changes_outside_the_distribution(
    release_repository: tuple[Path, Path, str],
) -> None:
    repository, dist, head = release_repository
    (repository / "untracked.py").write_text("print('not tagged')\n", encoding="utf-8")

    assert_rejected(invoke_guard(repository, dist, head), "changes outside the artifact bundle")
