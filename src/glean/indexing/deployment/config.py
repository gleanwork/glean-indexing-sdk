"""Deployment configuration model for glean-idx deploy."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

_CONNECTOR_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*", re.ASCII)
_KUBERNETES_DNS_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", re.ASCII)
_DNS_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
_CRONJOB_NAME_RE = _KUBERNETES_DNS_LABEL_RE
_GCP_SERVICE_ACCOUNT_RE = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", re.ASCII)
_AWS_IAM_ROLE_RE = re.compile(r"[A-Za-z0-9_+=,.@-]+", re.ASCII)
_GCP_IMAGE_COMPONENT_RE = re.compile(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*", re.ASCII)
_AWS_ECR_COMPONENT_RE = re.compile(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*", re.ASCII)
_IMAGE_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", re.ASCII)
_SCAFFOLD_REPOSITORY_PLACEHOLDERS = frozenset({"<account>", "<project>", "<region>"})


def _image_repository_path(image_name: str) -> str:
    """Return the repository path portion of a container image name, excluding its registry."""
    first_component, separator, remainder = image_name.partition("/")
    if separator and (
        "." in first_component or ":" in first_component or first_component == "localhost"
    ):
        return remainder
    return image_name


def _valid_repository_path(
    path: str, component_pattern: re.Pattern[str], min_length: int, max_length: int
) -> bool:
    return min_length <= len(path) <= max_length and all(
        component_pattern.fullmatch(component) or component in _SCAFFOLD_REPOSITORY_PLACEHOLDERS
        for component in path.split("/")
    )


class DeploymentConfig(BaseModel):
    """Configuration for a connector deployment (loaded from ``glean_deployment.yaml``)."""

    connector_name: str = Field(
        description="Unique deployment name, used as CronJob name and secret prefix."
    )
    connector_class: str = Field(description="Python class name of the connector.")
    connector_module: str = Field(description="Python module path containing the connector class.")
    connector_factory: Optional[str] = Field(
        default=None,
        description=(
            "Optional zero-argument factory in connector_module. The factory must return "
            "an instance of connector_class."
        ),
    )

    cloud: Literal["gcp", "aws"] = Field(description="Target cloud provider.")
    region: str = Field(
        description="Cloud region (e.g. 'us-central1' for GCP, 'us-east-1' for AWS)."
    )
    cluster_name: str = Field(description="Kubernetes cluster name.")
    namespace: str = Field(default="default", description="Kubernetes namespace for the CronJob.")
    image_tag: str = Field(default="latest", description="Container image tag to build and deploy.")

    cpu: str = Field(default="500m", description="Pod CPU request/limit (Kubernetes format).")
    memory: str = Field(
        default="512Mi", description="Pod memory request/limit (Kubernetes format)."
    )

    cron_schedule: str = Field(
        default="0 2 * * *", description="CronJob schedule (UTC cron expression)."
    )
    indexing_mode: str = Field(
        default="FULL", description="Indexing mode ('FULL' or 'INCREMENTAL')."
    )

    # GCP-specific
    project_id: str | None = Field(
        default=None, description="GCP project ID. Required when cloud=gcp."
    )
    artifact_registry_repo: str | None = Field(
        default=None, description="Artifact Registry repo URL. Required when cloud=gcp."
    )
    service_account_name: str | None = Field(
        default=None,
        description="GCP service account for Workload Identity. Defaults to <connector_name>-sa.",
    )
    cluster_endpoint: str | None = Field(
        default=None,
        description=(
            "Override the GKE cluster API endpoint used by Terraform's kubernetes provider. "
            "Required for private-only GKE clusters (enablePublicEndpoint: false) that expose a "
            "GKE DNS endpoint (*.gke.goog). Set this to the bare hostname only, e.g. "
            '"abc123.gke.goog" — Terraform prepends https:// automatically. '
            "Leave unset for clusters with a public IP endpoint."
        ),
    )

    # AWS-specific
    account_id: str | None = Field(
        default=None, description="AWS account ID. Required when cloud=aws."
    )
    ecr_repo: str | None = Field(
        default=None, description="ECR repository URI. Required when cloud=aws."
    )
    iam_role_name: str | None = Field(
        default=None, description="AWS IAM role name for IRSA. Defaults to <connector_name>-role."
    )

    @field_validator("account_id", mode="before")
    @classmethod
    def normalize_account_id(cls, v: object) -> object:
        """Normalize YAML integers and enforce the AWS 12-digit account-ID contract."""
        import re

        if v is None:
            return v
        if isinstance(v, int) and not isinstance(v, bool):
            v = str(v)
        if not isinstance(v, str) or re.fullmatch(r"[0-9]{12}", v) is None:
            raise ValueError("account_id must be exactly 12 decimal digits")
        return v

    @field_validator("connector_name")
    @classmethod
    def validate_connector_name(cls, v: str) -> str:
        """Validate connector_name is lowercase ASCII alphanumeric with underscores/hyphens."""
        if not _CONNECTOR_NAME_RE.fullmatch(v):
            raise ValueError(
                f"connector_name must be lowercase ASCII alphanumeric with underscores or hyphens, got: {v!r}"
            )
        return v

    @field_validator("image_tag")
    @classmethod
    def validate_image_tag(cls, v: str) -> str:
        """Validate the Docker image tag syntax and length."""
        if _IMAGE_TAG_RE.fullmatch(v) is None:
            raise ValueError(
                "image_tag must be 1-128 ASCII alphanumeric, underscore, period, or hyphen "
                "characters and must start with alphanumeric or underscore"
            )
        return v

    @field_validator("cluster_endpoint")
    @classmethod
    def validate_cluster_endpoint(cls, v: str | None) -> str | None:
        """Validate the optional GKE DNS endpoint as a bare hostname."""
        if v is None:
            return v
        labels = v.split(".")
        if (
            len(v) > 253
            or len(labels) < 2
            or any(_DNS_LABEL_RE.fullmatch(label) is None for label in labels)
        ):
            raise ValueError(
                "cluster_endpoint must be a bare DNS hostname without a scheme, port, path, or trailing dot"
            )
        return v

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        """Validate namespace as an ASCII Kubernetes DNS label."""
        if len(v) > 63 or not _KUBERNETES_DNS_LABEL_RE.fullmatch(v):
            raise ValueError(
                "namespace must be 1-63 ASCII lowercase alphanumeric or hyphen characters, "
                "starting and ending with alphanumeric"
            )
        return v

    @model_validator(mode="after")
    def validate_cloud_specific_fields(self) -> DeploymentConfig:
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

    @model_validator(mode="after")
    def validate_resource_names(self) -> DeploymentConfig:
        """Validate that derived Kubernetes, GCP, AWS, and image names satisfy provider constraints."""
        k8s_name = self.k8s_name
        if len(k8s_name) > 52 or not _CRONJOB_NAME_RE.fullmatch(k8s_name):
            raise ValueError(
                f"Derived Kubernetes CronJob name {k8s_name!r} is invalid "
                "(1-52 ASCII lowercase alphanumeric or hyphen characters, starting and ending with alphanumeric). "
                "Adjust connector_name."
            )

        account_name = self.effective_service_account
        if self.cloud == "gcp":
            if not _GCP_SERVICE_ACCOUNT_RE.fullmatch(account_name):
                if self.service_account_name is not None:
                    raise ValueError(
                        f"service_account_name {account_name!r} is invalid "
                        "(6-30 ASCII lowercase alphanumeric or hyphen characters, starting with a letter and ending with alphanumeric)."
                    )
                raise ValueError(
                    f"Derived GCP service account name {account_name!r} is invalid "
                    "(6-30 ASCII lowercase alphanumeric or hyphen characters, starting with a letter and ending with alphanumeric). "
                    "Set service_account_name explicitly or adjust connector_name."
                )

            repository_path = _image_repository_path(self.image_name)
            if not _valid_repository_path(repository_path, _GCP_IMAGE_COMPONENT_RE, 1, 255):
                raise ValueError(
                    f"Derived GCP Artifact Registry repository path {repository_path!r} is invalid "
                    "(1-255 ASCII lowercase repository-path characters with valid Docker path components). "
                    "Adjust artifact_registry_repo or connector_name."
                )

        else:
            if len(account_name) > 64 or not _AWS_IAM_ROLE_RE.fullmatch(account_name):
                if self.iam_role_name is not None:
                    raise ValueError(
                        f"iam_role_name {account_name!r} is invalid "
                        "(1-64 ASCII alphanumeric characters or _+=,.@-)."
                    )
                raise ValueError(
                    f"Derived AWS IAM role name {account_name!r} is invalid "
                    "(1-64 ASCII alphanumeric characters or _+=,.@-). "
                    "Set iam_role_name explicitly or adjust connector_name."
                )

            repository_path = _image_repository_path(self.image_name)
            if not _valid_repository_path(repository_path, _AWS_ECR_COMPONENT_RE, 2, 256):
                raise ValueError(
                    f"Derived AWS ECR repository path {repository_path!r} is invalid "
                    "(2-256 ASCII lowercase repository-path characters with valid separators and slash-delimited components). "
                    "Adjust ecr_repo or connector_name."
                )

        return self

    @classmethod
    def from_yaml(cls, path: Path) -> DeploymentConfig:
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
    def image_reference(self) -> str:
        """Full container image URI including the configured tag."""
        return f"{self.image_name}:{self.image_tag}"

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
