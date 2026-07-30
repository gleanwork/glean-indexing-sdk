"""Customer self-deployment toolkit for Glean custom connectors.

Provides the ``glean-deploy`` CLI and supporting utilities for generating
cloud-specific deployment artifacts (Dockerfile, Terraform, run.py) and
managing connector secrets in GCP or AWS.
"""

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import generate_artifacts
from glean.indexing.deployment.secrets import (
    AWSOAuth2TokenStore,
    GCPOAuth2TokenStore,
    get_oauth2_auth_provider_from_environment,
    get_oauth2_token_store_from_environment,
)

__all__ = [
    "AWSOAuth2TokenStore",
    "DeploymentConfig",
    "GCPOAuth2TokenStore",
    "generate_artifacts",
    "get_oauth2_auth_provider_from_environment",
    "get_oauth2_token_store_from_environment",
]
