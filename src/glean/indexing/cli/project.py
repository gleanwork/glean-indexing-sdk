"""Connector-project discovery and connector loading.

Some commands need only credentials and run anywhere. Others have to load *your*
connector class, which means running inside your project with the SDK installed
alongside your code. Getting that wrong is the most likely way to be confused by
this CLI, so the failures here are deliberately verbose: what was needed, where
we looked, and the exact command that fixes it.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from glean.indexing.cli.errors import ConnectorNotImportableError, NoProjectError

#: The file that marks a directory as a connector project. Written by
#: `glean-idx deploy init`, and the source of the connector's module and class.
PROJECT_FILE = "glean_deployment.yaml"

DOCS = "https://developers.glean.com/libraries/indexing-sdk/cli"


def _candidates(start: Path) -> list[Path]:
    """`start` and each ancestor, nearest first."""
    return [start, *start.parents]


def find_project(start: Optional[Path] = None) -> Optional[Path]:
    """The nearest directory at or above `start` holding a project file."""
    for directory in _candidates((start or Path.cwd()).resolve()):
        if (directory / PROJECT_FILE).is_file():
            return directory
    return None


def require_project(override: Optional[Path] = None, start: Optional[Path] = None) -> Path:
    """The project directory, or a failure naming every place we looked."""
    if override is not None:
        resolved = override.expanduser().resolve()
        if (resolved / PROJECT_FILE).is_file():
            return resolved
        raise NoProjectError(
            f"no {PROJECT_FILE} in {resolved}",
            detail=f"--project pointed at a directory with no {PROJECT_FILE}.",
            hint=[
                "check the path, or drop --project to search upward from here",
                "glean-idx deploy init --cloud gcp    create a project there",
            ],
            docs=DOCS,
        )

    origin = (start or Path.cwd()).resolve()
    found = find_project(origin)
    if found is not None:
        return found

    raise NoProjectError(
        "not inside a connector project",
        detail=(
            f"This command needs your connector, so it must run from the directory\n"
            f"holding {PROJECT_FILE} — or a subdirectory of it."
        ),
        searched=[str(path) for path in _candidates(origin)],
        hint=[
            "cd <your connector project>",
            "glean-idx <command> --project ~/path/to/connector",
            "glean-idx deploy init --cloud gcp    create a project here",
        ],
        docs=f"{DOCS}#projects",
    )


def load_project_config(project_dir: Path) -> dict[str, Any]:
    """Parse the project file, failing with its path on malformed YAML."""
    path = project_dir / PROJECT_FILE
    try:
        parsed = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise NoProjectError(
            f"could not parse {path}",
            detail=str(exc),
            hint=["fix the YAML syntax, or regenerate with glean-idx deploy init"],
            docs=DOCS,
        ) from exc
    return parsed if isinstance(parsed, dict) else {}


def isolated_run() -> bool:
    """Whether this looks like an ephemeral `uvx` environment.

    Used only to add a line to a failure message. `uv` leaves no dedicated
    marker, so this keys off the cache-backed prefix it runs from; a false
    negative costs one hint, never correctness.
    """
    return "/uv/" in sys.prefix.replace(os.sep, "/")


def load_connector(
    project_dir: Path,
    config: dict[str, Any],
    reference: Optional[str] = None,
) -> Any:
    """Import and instantiate the project's connector class.

    `reference` is an explicit ``module:Class`` override; otherwise the project
    file's ``connector_module`` and ``connector_class`` are used, which is what
    `deploy init` writes and what the generated entrypoint already imports.
    """
    if reference:
        module_name, _, class_name = reference.partition(":")
        if not module_name or not class_name:
            raise ConnectorNotImportableError(
                f"malformed connector reference {reference!r}",
                detail="Expected module:Class, for example connector:CompanyWikiConnector.",
                hint=["glean-idx <command> --connector connector:MyConnector"],
                docs=DOCS,
            )
    else:
        module_name = config.get("connector_module") or "connector"
        class_name = config.get("connector_class") or ""
        if not class_name:
            raise ConnectorNotImportableError(
                f"{PROJECT_FILE} does not name a connector class",
                detail="Set connector_class (and connector_module) in the project file.",
                hint=[
                    "add connector_class: MyConnector to " + PROJECT_FILE,
                    "glean-idx <command> --connector connector:MyConnector",
                ],
                docs=DOCS,
            )

    module = _import_from_project(project_dir, module_name)
    connector_class = getattr(module, class_name, None)
    if connector_class is None:
        available = sorted(
            name
            for name, value in vars(module).items()
            if isinstance(value, type) and not name.startswith("_")
        )
        raise ConnectorNotImportableError(
            f"{module_name!r} has no class named {class_name!r}",
            detail="Classes found in that module: " + (", ".join(available) or "none"),
            hint=[f"glean-idx <command> --connector {module_name}:<ClassName>"],
            docs=DOCS,
        )
    return connector_class


def _import_from_project(project_dir: Path, module_name: str) -> Any:
    """Import `module_name` with the project directory on the path.

    A console script starts with its own bin directory on `sys.path`, never the
    working directory, so the project has to be added explicitly — the same
    thing pytest and uvicorn do to load user code.
    """
    root = str(project_dir)
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        # Drop a cached module that came from somewhere else, so the project's
        # own file wins. Without this a stale import from a different directory
        # is returned silently — the project on disk is the source of truth.
        _evict_foreign_module(module_name, project_dir)
        importlib.invalidate_caches()
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name != module_name:
            # The connector imported successfully but one of *its* dependencies
            # is absent — a different problem, and a different fix.
            raise ConnectorNotImportableError(
                f"{module_name!r} needs {exc.name!r}, which is not installed",
                detail=_environment_note(),
                hint=[
                    f"install the connector's dependencies (uv add {exc.name})",
                    "then re-run with uv run glean-idx <command>",
                ],
                docs=DOCS,
            ) from exc
        raise ConnectorNotImportableError(
            f"cannot import connector module {module_name!r}",
            detail=_environment_note(),
            hint=[
                f"confirm {module_name}.py exists in {project_dir}",
                "uv add glean-indexing-sdk && uv run glean-idx <command>",
            ],
            docs=DOCS,
        ) from exc
    finally:
        if added:
            sys.path.remove(root)


def _evict_foreign_module(module_name: str, project_dir: Path) -> None:
    """Forget an already-imported module that does not live in this project."""
    cached = sys.modules.get(module_name)
    if cached is None:
        return
    origin = getattr(cached, "__file__", None)
    if origin is None or project_dir not in Path(origin).resolve().parents:
        del sys.modules[module_name]


def _environment_note() -> str:
    note = (
        "This command imports your connector, so the SDK must be installed in the\n"
        "same environment as your code."
    )
    if isolated_run():
        note += "\n\nThis looks like an isolated run (uvx), which cannot see your project."
    return note
