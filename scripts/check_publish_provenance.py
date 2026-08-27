#!/usr/bin/env python3
"""Verify that release artifacts came from the exact tagged SDK commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import NoReturn

VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
TAG_PATTERN = re.compile(rf"v{VERSION_PATTERN.pattern}")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
VERSION_SOURCES = {
    "pyproject.toml": re.compile(r'^\[project\]\s*$[\s\S]*?^version\s*=\s*"([^"]+)"', re.MULTILINE),
    ".cz.toml": re.compile(
        r'^\[tool\.commitizen\]\s*$[\s\S]*?^version\s*=\s*"([^"]+)"', re.MULTILINE
    ),
    "src/glean/indexing/__init__.py": re.compile(r'^\s*__version__\s*=\s*"([^"]+)"', re.MULTILINE),
}
PROJECT_PATTERN = re.compile(r'^\[project\]\s*$[\s\S]*?^name\s*=\s*"([^"]+)"', re.MULTILINE)


class ProvenanceError(Exception):
    """A release input is not bound to the expected source."""


def fail(message: str) -> NoReturn:
    """Raise a provenance validation failure."""
    raise ProvenanceError(message)


def git(*args: str) -> str:
    """Run Git in the release checkout."""
    try:
        return subprocess.run(
            ("git", *args), check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "Git command failed"
        fail(detail)


def source_value(path: Path, pattern: re.Pattern[str], label: str) -> str:
    """Read one required value from a release source file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"Could not read {label} from {path}: {error}")
    value = pattern.search(text)
    if value is None:
        fail(f"Could not read {label} from {path}.")
    return value.group(1)


def canonical_name(name: str) -> str:
    """Return the package-index canonical project name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def metadata_values(text: str, artifact: Path) -> tuple[str, str]:
    """Read and validate project metadata from an artifact."""
    metadata = Parser().parsestr(text)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        fail(f"{artifact.name} metadata must contain Name and Version.")
    return name, version


def wheel_metadata(wheel: Path) -> tuple[str, str]:
    """Read the single wheel METADATA record."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            records = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(records) != 1:
                fail(f"{wheel.name} must contain exactly one .dist-info/METADATA record.")
            return metadata_values(archive.read(records[0]).decode("utf-8"), wheel)
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        fail(f"Could not inspect {wheel.name}: {error}")


def sdist_metadata(sdist: Path) -> tuple[str, str]:
    """Read the single top-level sdist PKG-INFO record."""
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            records = [
                member
                for member in archive.getmembers()
                if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
            ]
            if len(records) != 1:
                fail(f"{sdist.name} must contain exactly one top-level PKG-INFO record.")
            extracted = archive.extractfile(records[0])
            if extracted is None:
                fail(f"Could not read {records[0].name} from {sdist.name}.")
            return metadata_values(extracted.read().decode("utf-8"), sdist)
    except (OSError, UnicodeDecodeError, tarfile.TarError) as error:
        fail(f"Could not inspect {sdist.name}: {error}")


def sha256(path: Path) -> str:
    """Hash an artifact without loading it all into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        fail(f"Could not hash {path}: {error}")
    return digest.hexdigest()


def validate_checkout(tag: str, expected_sha: str, allowed_untracked: tuple[Path, ...]) -> None:
    """Bind the checkout and tag to the event commit."""
    if TAG_PATTERN.fullmatch(tag) is None:
        fail(f"Release tag must exactly match v<version>; got {tag!r}.")
    if SHA_PATTERN.fullmatch(expected_sha) is None:
        fail(f"Release commit must be a full lowercase SHA; got {expected_sha!r}.")

    head = git("rev-parse", "HEAD")
    if head != expected_sha:
        fail(f"Checked-out HEAD {head} does not match release commit {expected_sha}.")
    tag_commit = git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    if tag_commit != expected_sha:
        fail(f"Tag {tag} points to {tag_commit}, not release commit {expected_sha}.")

    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    dirty = git("status", "--porcelain", "--untracked-files=all")
    unexpected = []
    for entry in dirty.splitlines():
        candidate = (root / entry[3:]).resolve()
        if not any(
            candidate == allowed or allowed in candidate.parents for allowed in allowed_untracked
        ):
            unexpected.append(entry)
    if unexpected:
        fail(
            "Release checkout contains changes outside the artifact bundle:\n"
            + "\n".join(unexpected)
        )


def validate_sources(tag: str) -> tuple[str, str]:
    """Require every SDK version source to match the event tag."""
    versions = {
        path: source_value(Path(path), pattern, f"version in {path}")
        for path, pattern in VERSION_SOURCES.items()
    }
    if len(set(versions.values())) != 1:
        fail(
            "SDK version sources differ: "
            + ", ".join(f"{path}={version}" for path, version in versions.items())
            + "."
        )
    version = next(iter(versions.values()))
    if VERSION_PATTERN.fullmatch(version) is None:
        fail(f"SDK version {version!r} is not a supported release version.")
    if tag != f"v{version}":
        fail(f"Release tag {tag} does not match SDK version {version}.")
    project = source_value(Path("pyproject.toml"), PROJECT_PATTERN, "project name")
    return project, version


def validate_artifacts(dist: Path, project: str, version: str) -> dict[str, str]:
    """Require exactly one matching wheel and source distribution."""
    try:
        files = sorted(path for path in dist.iterdir() if path.is_file())
    except OSError as error:
        fail(f"Could not read artifact directory {dist}: {error}")
    wheels = [path for path in files if path.suffix == ".whl"]
    sdists = [path for path in files if path.name.endswith(".tar.gz")]
    unexpected = [path.name for path in files if path not in wheels and path not in sdists]
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        fail(
            f"Artifact directory must contain exactly one wheel and one .tar.gz sdist; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}, unexpected={unexpected}."
        )

    expected_stem = canonical_name(project).replace("-", "_")
    wheel, sdist = wheels[0], sdists[0]
    if not wheel.name.startswith(f"{expected_stem}-{version}-"):
        fail(f"Wheel filename {wheel.name} does not match {project} {version}.")
    if sdist.name != f"{expected_stem}-{version}.tar.gz":
        fail(f"Sdist filename {sdist.name} does not match {project} {version}.")

    for artifact, (name, artifact_version) in (
        (wheel, wheel_metadata(wheel)),
        (sdist, sdist_metadata(sdist)),
    ):
        if canonical_name(name) != canonical_name(project) or artifact_version != version:
            fail(
                f"{artifact.name} metadata is {name} {artifact_version}; "
                f"expected {project} {version}."
            )
    return {path.name: sha256(path) for path in (wheel, sdist)}


def parse_args() -> argparse.Namespace:
    """Parse command-line inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Exact event tag, such as v1.2.3")
    parser.add_argument("--sha", required=True, help="Exact 40-character event commit SHA")
    parser.add_argument(
        "--dist", required=True, type=Path, help="Directory containing the built wheel and sdist"
    )
    manifest = parser.add_mutually_exclusive_group()
    manifest.add_argument(
        "--write-manifest", type=Path, help="Write verified provenance for artifact transfer"
    )
    manifest.add_argument(
        "--verify-manifest", type=Path, help="Verify transferred artifacts against this manifest"
    )
    return parser.parse_args()


def main() -> None:
    """Validate release provenance and optionally write or verify its manifest."""
    args = parse_args()
    dist = args.dist.resolve()
    allowed = [dist]
    if args.write_manifest:
        allowed.append(args.write_manifest.resolve())
    if args.verify_manifest:
        allowed.append(args.verify_manifest.resolve())
    validate_checkout(args.tag, args.sha, tuple(allowed))
    project, version = validate_sources(args.tag)
    provenance = {
        "artifacts": validate_artifacts(dist, project, version),
        "commit": args.sha,
        "project": project,
        "tag": args.tag,
        "version": version,
    }

    if args.verify_manifest:
        try:
            expected = json.loads(args.verify_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            fail(f"Could not read provenance manifest {args.verify_manifest}: {error}")
        if expected != provenance:
            fail(
                "Transferred artifact provenance does not match the verified checkout and artifact hashes."
            )
    if args.write_manifest:
        try:
            args.write_manifest.write_text(
                json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError as error:
            fail(f"Could not write provenance manifest {args.write_manifest}: {error}")

    print(f"Verified {project} {version} at {args.tag} ({args.sha}).")


if __name__ == "__main__":
    try:
        main()
    except ProvenanceError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
