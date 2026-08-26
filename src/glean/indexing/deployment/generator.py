"""Deployment artifact generator for glean-idx deploy."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from glean.indexing.deployment.config import DeploymentConfig

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_GITIGNORE_PROTECTIONS = (b".env", b".terraform/", b"*.tfstate*")

_GCP_ARTIFACTS: list[tuple[str, str]] = [
    ("Dockerfile", "gcp/Dockerfile.j2"),
    ("run.py", "gcp/run.py.j2"),
    ("terraform/main.tf", "gcp/main.tf.j2"),
    ("terraform/variables.tf", "gcp/variables.tf.j2"),
]

_AWS_ARTIFACTS: list[tuple[str, str]] = [
    ("Dockerfile", "aws/Dockerfile.j2"),
    ("run.py", "aws/run.py.j2"),
    ("terraform/main.tf", "aws/main.tf.j2"),
    ("terraform/variables.tf", "aws/variables.tf.j2"),
]

_COMMON_ARTIFACTS: list[tuple[str, str]] = [
    ("glean_deployment.yaml", "common/glean_deployment.yaml.j2"),
    (".env.example", "common/env_example.j2"),
    (".dockerignore", "common/dockerignore.j2"),
]


def _make_env() -> Environment:
    """Create the Jinja2 environment pointed at the templates directory."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def _render_template(env: Environment, template_path: str, context: dict[str, Any]) -> str:
    """Render a single template and return the result string."""
    return env.get_template(template_path).render(**context)


def _path_exists(path: Path) -> bool:
    """Return whether a path or dangling symlink occupies this location."""
    return path.exists() or path.is_symlink()


def _generated_path_blockers(output_dir: Path, artifacts: dict[str, str]) -> list[str]:
    """Find destinations that cannot safely be generated, even with ``force=True``."""
    blockers: list[str] = []
    if _path_exists(output_dir) and (output_dir.is_symlink() or not output_dir.is_dir()):
        blockers.append(".")

    for rel_path in artifacts:
        destination = output_dir / rel_path
        if _path_exists(destination) and (destination.is_symlink() or not destination.is_file()):
            blockers.append(rel_path)
            continue

        parent = destination.parent
        while parent != output_dir:
            if _path_exists(parent) and (parent.is_symlink() or not parent.is_dir()):
                blockers.append(parent.relative_to(output_dir).as_posix())
                break
            parent = parent.parent

    gitignore = output_dir / ".gitignore"
    if _path_exists(gitignore) and (gitignore.is_symlink() or not gitignore.is_file()):
        blockers.append(".gitignore")
    return list(dict.fromkeys(blockers))


def _generated_path_collisions(output_dir: Path, artifacts: dict[str, str]) -> list[str]:
    """Find every generated file path already occupied by user content."""
    return [rel_path for rel_path in artifacts if _path_exists(output_dir / rel_path)]


def _merged_gitignore(output_dir: Path) -> bytes | None:
    """Prepare a merged .gitignore, or return ``None`` when no update is needed."""
    gitignore = output_dir / ".gitignore"
    if _path_exists(gitignore) and (gitignore.is_symlink() or not gitignore.is_file()):
        raise FileExistsError(
            f"Cannot safely update {gitignore}: expected a regular file, not a directory or symlink."
        )

    existing = gitignore.read_bytes() if gitignore.exists() else b""
    existing_lines = set(existing.splitlines())
    missing = [rule for rule in _GITIGNORE_PROTECTIONS if rule not in existing_lines]
    if not missing:
        return None

    newline = (
        b"\r\n" if b"\r\n" in existing and b"\n" not in existing.replace(b"\r\n", b"") else b"\n"
    )
    separator = b"" if not existing or existing.endswith((b"\n", b"\r")) else newline
    return existing + separator + newline.join(missing) + newline


def _atomic_write(destination: Path, content: bytes) -> None:
    """Atomically replace one regular file using a temporary sibling."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = (
        stat.S_IMODE(destination.stat().st_mode)
        if destination.exists() and not destination.is_symlink()
        else None
    )
    for _ in range(10):
        temporary = destination.parent / f".{destination.name}.{secrets.token_hex(8)}"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            continue
        break
    else:
        raise OSError(f"Could not allocate a temporary file beside {destination}")

    try:
        with os.fdopen(fd, "wb") as temporary_file:
            temporary_file.write(content)
        if existing_mode is not None:
            temporary.chmod(existing_mode)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_artifacts(output_dir: Path, artifacts: dict[str, str], gitignore: bytes | None) -> None:
    """Write pre-rendered deployment artifacts and the prepared .gitignore merge."""
    for rel_path, content in artifacts.items():
        _atomic_write(output_dir / rel_path, content.encode("utf-8"))
    if gitignore is not None:
        _atomic_write(output_dir / ".gitignore", gitignore)


def _write_generated_artifacts(output_dir: Path, artifacts: dict[str, str], *, force: bool) -> None:
    """Preflight and write a complete set of rendered deployment artifacts."""
    blockers = _generated_path_blockers(output_dir, artifacts)
    collisions = _generated_path_collisions(output_dir, artifacts)
    if not force and (collisions or blockers):
        conflicts = list(dict.fromkeys([*collisions, *blockers]))
        formatted = "\n".join(f"  {rel_path}" for rel_path in conflicts)
        raise FileExistsError(
            "Refusing to overwrite existing files or blocked paths:\n"
            f"{formatted}\n"
            "Pass force=True (CLI: --force) to overwrite generated files. "
            "Directories, symlinks, and non-directory parent paths must be moved first."
        )
    if blockers:
        formatted = "\n".join(f"  {rel_path}" for rel_path in blockers)
        raise FileExistsError(
            "force=True / --force cannot replace directories, symlinks, special files, "
            f"or non-directory parent paths:\n{formatted}"
        )

    gitignore = _merged_gitignore(output_dir)
    _write_artifacts(output_dir, artifacts, gitignore)


def generate_artifacts(
    config: DeploymentConfig, output_dir: Path | None = None, *, force: bool = False
) -> dict[str, str]:
    """Render all deployment artifacts for the given config.

    Output is deterministic: the same config always produces identical rendered
    content. When ``output_dir`` is provided, the function preflights every
    destination, refuses to overwrite by default, protects local deployment
    secrets via ``.gitignore``, and replaces each regular file atomically using
    a temporary sibling. Pass ``force=True`` to replace existing regular files.

    Atomicity here is intended for ordinary local generator use and applies to
    each file replacement, not the artifact set as a filesystem transaction.
    Concurrent or hostile filesystem changes between preflight and replacement
    are outside this API's guarantees.

    Args:
        config: Deployment configuration used to render templates.
        output_dir: Optional directory in which to write rendered artifacts.
        force: Whether to replace existing generated regular files.

    Returns:
        A mapping from relative output paths to rendered content.

    Raises:
        FileExistsError: If a destination is occupied without ``force=True``,
            or cannot safely be replaced with a regular file.
    """
    env = _make_env()
    context = {"config": config}

    cloud_artifacts = _GCP_ARTIFACTS if config.cloud == "gcp" else _AWS_ARTIFACTS
    all_artifacts = cloud_artifacts + _COMMON_ARTIFACTS

    rendered: dict[str, str] = {}
    for output_path, template_path in all_artifacts:
        rendered[output_path] = _render_template(env, template_path, context)

    if output_dir is not None:
        _write_generated_artifacts(output_dir, rendered, force=force)

    return rendered


def list_generated_files(cloud: str) -> list[str]:
    """Return the relative output paths that would be generated for a given cloud target."""
    if cloud == "gcp":
        cloud_artifacts = _GCP_ARTIFACTS
    elif cloud == "aws":
        cloud_artifacts = _AWS_ARTIFACTS
    else:
        raise ValueError(f"Unsupported cloud target: {cloud!r}. Must be 'gcp' or 'aws'.")
    return [path for path, _ in cloud_artifacts + _COMMON_ARTIFACTS]
