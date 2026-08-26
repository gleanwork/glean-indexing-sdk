"""Deployment artifact generator for glean-idx deploy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from glean.indexing.deployment.config import DeploymentConfig

_TEMPLATES_DIR = Path(__file__).parent / "templates"

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


def generate_artifacts(config: DeploymentConfig, output_dir: Path | None = None, force: bool = False) -> dict[str, str]:
    """Render all deployment artifacts for the given config.

    Returns a dict mapping relative output path to rendered content.
    If ``output_dir`` is given, also writes the files to disk.
    Output is deterministic — same config always produces identical files.

    Raises ``FileExistsError`` if any destination file already exists and ``force`` is False.
    """
    env = _make_env()
    context = {"config": config}

    cloud_artifacts = _GCP_ARTIFACTS if config.cloud == "gcp" else _AWS_ARTIFACTS
    all_artifacts = cloud_artifacts + _COMMON_ARTIFACTS

    rendered: dict[str, str] = {}
    for output_path, template_path in all_artifacts:
        rendered[output_path] = _render_template(env, template_path, context)

    if output_dir is not None:
        if not force:
            conflicts = [rel for rel in rendered if (output_dir / rel).exists()]
            if conflicts:
                names = "\n  ".join(conflicts)
                raise FileExistsError(
                    f"Destination already contains generated files:\n  {names}\n"
                    "Re-run with --force to overwrite."
                )
        for rel_path, content in rendered.items():
            dest = output_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")

        _merge_gitignore(output_dir)

    return rendered


_GITIGNORE_ENTRIES = [".env", ".env.*", ".terraform/", "*.tfstate*", "*.tfvars"]


def _merge_gitignore(output_dir: Path) -> None:
    """Append any missing glean-deploy entries to .gitignore without replacing user content."""
    gitignore = output_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [e for e in _GITIGNORE_ENTRIES if e not in existing_lines]
    if missing:
        separator = "\n" if existing and not existing.endswith("\n") else ""
        gitignore.write_text(
            existing + separator + "\n".join(missing) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def list_generated_files(cloud: str) -> list[str]:
    """Return the relative output paths that would be generated for a given cloud target."""
    if cloud == "gcp":
        cloud_artifacts = _GCP_ARTIFACTS
    elif cloud == "aws":
        cloud_artifacts = _AWS_ARTIFACTS
    else:
        raise ValueError(f"Unsupported cloud target: {cloud!r}. Must be 'gcp' or 'aws'.")
    return [path for path, _ in cloud_artifacts + _COMMON_ARTIFACTS]
