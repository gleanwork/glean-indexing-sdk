"""Verify generated deployment Terraform is formatted and valid."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from glean.indexing.deployment import generate_artifacts
from glean.indexing.deployment.config import DeploymentConfig

_CONFIGS = (
    DeploymentConfig(
        connector_name="format_check",
        connector_class="FormatCheckConnector",
        connector_module="connector",
        connector_factory="create_connector",
        cloud="gcp",
        region="us-central1-a",
        cluster_name="format-check",
        namespace="format-check",
        project_id="format-check-project",
        artifact_registry_repo=("us-central1-docker.pkg.dev/format-check-project/glean-connectors"),
        cluster_endpoint="format-check.us-central1-a.gke.goog",
    ),
    DeploymentConfig(
        connector_name="format_check",
        connector_class="FormatCheckConnector",
        connector_module="connector",
        connector_factory="create_connector",
        cloud="aws",
        region="us-east-1",
        cluster_name="format-check",
        namespace="format-check",
        account_id="123456789012",
        ecr_repo="123456789012.dkr.ecr.us-east-1.amazonaws.com/glean-connectors",
    ),
)


def main() -> None:
    """Generate both cloud variants and run Terraform formatting and validation."""
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        for config in _CONFIGS:
            cloud_root = root / config.cloud
            for relative_path, content in generate_artifacts(config).items():
                if not relative_path.startswith("terraform/"):
                    continue
                output_path = cloud_root / relative_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content)

        subprocess.run(
            ["terraform", "fmt", "-check", "-diff", "-recursive", str(root)],
            check=True,
        )
        for config in _CONFIGS:
            terraform_directory = root / config.cloud / "terraform"
            subprocess.run(
                ["terraform", "init", "-backend=false", "-input=false"],
                cwd=terraform_directory,
                check=True,
            )
            subprocess.run(
                ["terraform", "validate"],
                cwd=terraform_directory,
                check=True,
            )


if __name__ == "__main__":
    main()
