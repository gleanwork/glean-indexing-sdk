"""Customer self-deployment toolkit for Glean custom connectors.

Provides the ``glean-deploy`` CLI and supporting utilities for generating
cloud-specific deployment artifacts (Dockerfile, Terraform, run.py) and
managing connector secrets in GCP or AWS.
"""

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import generate_artifacts

__all__ = [
    "DeploymentConfig",
    "generate_artifacts",
]
