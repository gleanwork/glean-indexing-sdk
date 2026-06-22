"""Deployment configuration model for glean-deploy."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class DeploymentConfig(BaseModel):
    """Configuration for a connector deployment (loaded from ``glean_deployment.yaml``)."""

    connector_name: str = Field(description="Unique deployment name, used as CronJob name and secret prefix.")
    connector_class: str = Field(description="Python class name of the connector.")
    connector_module: str = Field(description="Python module path containing the connector class.")

    cloud: Literal["gcp", "aws"] = Field(description="Target cloud provider.")
    region: str = Field(description="Cloud region (e.g. 'us-central1' for GCP, 'us-east-1' for AWS).")
    cluster_name: str = Field(description="Kubernetes cluster name.")
    namespace: str = Field(default="default", description="Kubernetes namespace for the CronJob.")

    cpu: str = Field(default="500m", description="Pod CPU request/limit (Kubernetes format).")
    memory: str = Field(default="512Mi", description="Pod memory request/limit (Kubernetes format).")

    cron_schedule: str = Field(default="0 2 * * *", description="CronJob schedule (UTC cron expression).")
    indexing_mode: str = Field(default="FULL", description="Indexing mode ('FULL' or 'INCREMENTAL').")

    # GCP-specific
    project_id: Optional[str] = Field(default=None, description="GCP project ID. Required when cloud=gcp.")
    artifact_registry_repo: Optional[str] = Field(default=None, description="Artifact Registry repo URL. Required when cloud=gcp.")
    service_account_name: Optional[str] = Field(default=None, description="GCP service account for Workload Identity. Defaults to <connector_name>-sa.")

    # AWS-specific
    account_id: Optional[str] = Field(default=None, description="AWS account ID. Required when cloud=aws.")
    ecr_repo: Optional[str] = Field(default=None, description="ECR repository URI. Required when cloud=aws.")
    iam_role_name: Optional[str] = Field(default=None, description="AWS IAM role name for IRSA. Defaults to <connector_name>-role.")

    @field_validator("connector_name")
    @classmethod
    def validate_connector_name(cls, v: str) -> str:
        """Validate connector_name is lowercase alphanumeric with underscores/hyphens."""
        import re

        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(
                f"connector_name must be lowercase alphanumeric with underscores or hyphens, got: {v!r}"
            )
        return v

    @model_validator(mode="after")
    def validate_cloud_specific_fields(self) -> "DeploymentConfig":
        """Validate that required cloud-specific fields are present."""
        if self.cloud == "gcp":
            if not self.project_id:
                raise ValueError("project_id is required when cloud=gcp")
            if not self.artifact_registry_repo:
                raise ValueError("artifact_registry_repo is required when cloud=gcp")
        elif self.cloud == "aws":
            if not self.account_id:
                raise ValueError("account_id is required when cloud=aws")
            if not self.ecr_repo:
                raise ValueError("ecr_repo is required when cloud=aws")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "DeploymentConfig":
        """Load and validate a DeploymentConfig from a YAML file."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """Write this config to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(exclude_none=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    @property
    def k8s_name(self) -> str:
        """Kubernetes-safe name derived from connector_name (underscores → hyphens)."""
        return self.connector_name.replace("_", "-")

    @property
    def image_name(self) -> str:
        """Full container image URI (registry/connector_name)."""
        if self.cloud == "gcp" and self.artifact_registry_repo:
            return f"{self.artifact_registry_repo}/{self.connector_name}"
        if self.cloud == "aws" and self.ecr_repo:
            return f"{self.ecr_repo}/{self.connector_name}"
        return self.connector_name

    @property
    def secret_prefix(self) -> str:
        """Secret name prefix in cloud secret manager."""
        return f"CUSTOM_DATASOURCE_PLATFORM_{self.connector_name.upper()}_"

    @property
    def effective_service_account(self) -> str:
        """GCP service account or AWS IAM role name, with k8s_name-based default."""
        if self.cloud == "gcp":
            return self.service_account_name or f"{self.k8s_name}-sa"
        return self.iam_role_name or f"{self.k8s_name}-role"
