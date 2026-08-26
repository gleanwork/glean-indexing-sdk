"""Build generated deployment images and verify their runtime UID/GID."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import generate_artifacts

_EXPECTED_ID = "1000:1000"


def _config(cloud: Literal["aws", "gcp"]) -> DeploymentConfig:
    if cloud == "aws":
        return DeploymentConfig(
            connector_name="security_smoke",
            connector_class="SmokeConnector",
            connector_module="connector",
            cloud="aws",
            region="us-east-1",
            cluster_name="smoke-cluster",
            account_id="123456789012",
            ecr_repo="123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors",
        )
    return DeploymentConfig(
        connector_name="security_smoke",
        connector_class="SmokeConnector",
        connector_module="connector",
        cloud="gcp",
        region="us-central1",
        cluster_name="smoke-cluster",
        project_id="smoke-project",
        artifact_registry_repo="us-central1-docker.pkg.dev/smoke-project/connectors",
    )


def _write_context(root: Path, cloud: Literal["aws", "gcp"]) -> None:
    for relative_path, content in generate_artifacts(_config(cloud)).items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "deployment-security-smoke"\nversion = "0.0.0"\n'
        'requires-python = ">=3.10"\ndependencies = []\n'
    )


def _verify_cloud(root: Path, cloud: Literal["aws", "gcp"]) -> None:
    context = root / cloud
    context.mkdir()
    _write_context(context, cloud)
    image = f"glean-indexing-sdk-{cloud}-security-smoke"
    try:
        subprocess.run(
            ["docker", "build", "--tag", image, "."],
            cwd=context,
            check=True,
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                image,
                "-c",
                'printf \'%s:%s\' "$(id -u)" "$(id -g)"',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        actual = result.stdout.strip()
        if actual != _EXPECTED_ID:
            raise RuntimeError(f"{cloud} image ran as {actual}, expected {_EXPECTED_ID}")
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="glean-deployment-user-") as temp_dir:
        root = Path(temp_dir)
        for cloud in ("aws", "gcp"):
            _verify_cloud(root, cloud)
            print(f"{cloud}: generated image runs as {_EXPECTED_ID}")


if __name__ == "__main__":
    main()
