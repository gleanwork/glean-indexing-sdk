"""Validated local manifest of connector secret environment keys."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)
MANIFEST_FILENAME = ".glean_secret_keys"


def validate_env_key(key: str) -> str:
    """Return *key* when it is safe to use as an environment variable name."""
    if not _ENV_KEY_RE.fullmatch(key):
        raise ValueError(
            f"Environment variable key {key!r} is invalid "
            "(use ASCII letters, numbers, and underscores; do not start with a number)."
        )
    return key


def manifest_path(config_path: Path) -> Path:
    """Return the secret manifest beside a deployment configuration file."""
    return config_path.parent / MANIFEST_FILENAME


def env_keys_from_upload_results(results: Mapping[str, str], secret_prefix: str) -> list[str]:
    """Convert a backend upload result's full cloud names to validated ENV keys."""
    keys: list[str] = []
    for secret_name in results:
        if not secret_name.startswith(secret_prefix):
            raise ValueError(
                f"Uploaded secret name {secret_name!r} does not belong to prefix {secret_prefix!r}."
            )
        keys.append(validate_env_key(secret_name.removeprefix(secret_prefix)))
    return sorted(set(keys))


def read_manifest(path: Path) -> list[str]:
    """Read, validate, and deterministically order manifest keys; missing means empty."""
    if not path.exists():
        return []
    return sorted(
        {validate_env_key(line.strip()) for line in path.read_text().splitlines() if line.strip()}
    )


def write_manifest(path: Path, keys: Iterable[str]) -> None:
    """Atomically replace *path* with sorted validated keys, including an empty file."""
    normalized = sorted({validate_env_key(key) for key in keys})
    content = ("\n".join(normalized) + ("\n" if normalized else "")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = (
        stat.S_IMODE(path.stat().st_mode) if path.exists() and not path.is_symlink() else None
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        if existing_mode is not None:
            temporary.chmod(existing_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
