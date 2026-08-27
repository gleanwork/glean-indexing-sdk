"""Cloud secret manager backends for glean-idx deploy.

Each cloud platform has a dedicated backend class (GCPSecretsBackend,
AWSSecretsBackend) sharing a common SecretsBackend interface. Use
get_secrets_backend(config) to obtain the right one at runtime.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from glean.indexing.deployment.secret_manifest import validate_env_key

if TYPE_CHECKING:
    from glean.indexing.deployment.config import DeploymentConfig

# Variables that control deployment runtime — never uploaded as connector secrets.
# Ref: https://cloud.google.com/secret-manager/docs
# Ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html
_REDLIST: frozenset[str] = frozenset(
    [
        "GOOGLE_CLOUD_PROJECT",
        "AWS_REGION",
        "DATASOURCE_NAME",
        "CLOUD_PLATFORM",
        "INDEXING_MODE",
        "SECRET_KEYS_JSON",
        "CONNECTOR_CLASS",
        "CONNECTOR_MODULE",
        "CONNECTOR_FACTORY",
    ]
)
_GCP_SECRET_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,255}", re.ASCII)
_AWS_SECRET_NAME_RE = re.compile(r"[A-Za-z0-9/_+=.@-]{1,512}", re.ASCII)


def parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse a .env file and return key-value pairs (comments and blank lines excluded).

    Keys present without a value (e.g. ``FOO`` with no ``=``) are omitted rather than
    mapped to ``None``, keeping the return type strictly ``dict[str, str]``.
    """
    from dotenv import dotenv_values

    raw = dotenv_values(env_file)
    return {k: v for k, v in raw.items() if v is not None}


def filter_secrets(env_vars: dict[str, str]) -> dict[str, str]:
    """Remove deployment-control variables (redlist) from an env var dict."""
    return {k: v for k, v in env_vars.items() if k not in _REDLIST}


class SecretsBackend(ABC):
    """Common interface for cloud-specific secret manager backends.

    Concrete implementations: GCPSecretsBackend, AWSSecretsBackend.
    Obtain one via get_secrets_backend(config).
    """

    def __init__(self, config: DeploymentConfig) -> None:
        self._config = config

    def _secret_name(self, env_key: str) -> str:
        """Build and validate the full cloud secret name: CUSTOM_DATASOURCE_PLATFORM_<NAME>_<KEY>."""
        validate_env_key(env_key)
        secret_name = f"{self._config.secret_prefix}{env_key}"
        self._validate_secret_name(secret_name)
        return secret_name

    def _validate_secret_name(self, secret_name: str) -> None:
        if self._config.cloud == "gcp":
            if not _GCP_SECRET_NAME_RE.fullmatch(secret_name):
                raise ValueError(
                    f"GCP secret name {secret_name!r} is invalid "
                    "(1-255 ASCII letters, numbers, hyphens, or underscores)."
                )
        elif not _AWS_SECRET_NAME_RE.fullmatch(secret_name):
            raise ValueError(
                f"AWS secret name {secret_name!r} is invalid "
                "(1-512 ASCII letters, numbers, or /_+=.@-)."
            )

    def _secret_entries(self, env_vars: dict[str, str]) -> list[tuple[str, str]]:
        """Validate every complete name before returning entries for a cloud operation."""
        return [(self._secret_name(key), value) for key, value in env_vars.items()]

    @abstractmethod
    def upload(self, env_file: Path) -> dict[str, str]:
        """Upload secrets from *env_file* to the cloud secret manager.

        Idempotent — creates new secrets and updates existing ones.
        Returns a mapping of ``{secret_name: "created" | "updated"}``.
        """

    @abstractmethod
    def list(self) -> list[str]:
        """Return sorted env-var key names for all connector secrets in the cloud."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Permanently delete the secret for env-var *key*.

        Raises:
            KeyError: if the secret does not exist.
        """


class GCPSecretsBackend(SecretsBackend):
    """GCP Secret Manager backend (beta).

    Requires the ``gcp`` extra: ``uv add glean-indexing-sdk[gcp]``.
    Ref: https://cloud.google.com/secret-manager/docs
    """

    def upload(self, env_file: Path) -> dict[str, str]:
        if not self._config.project_id:
            raise ValueError("project_id is required for GCP secret upload")

        env_vars = filter_secrets(parse_env_file(env_file))
        if not env_vars:
            return {}
        secret_entries = self._secret_entries(env_vars)

        from google.api_core.exceptions import NotFound
        from google.cloud.secretmanager import SecretManagerServiceClient

        client = SecretManagerServiceClient()
        parent = f"projects/{self._config.project_id}"
        results: dict[str, str] = {}

        for secret_id, value in secret_entries:
            secret_path = f"{parent}/secrets/{secret_id}"

            secret_existed = True
            try:
                client.get_secret(request={"name": secret_path})
            except NotFound:
                secret_existed = False
                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )

            client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": value.encode("utf-8")},
                }
            )
            results[secret_id] = "updated" if secret_existed else "created"

        return results

    def list(self) -> list[str]:
        if not self._config.project_id:
            raise ValueError("project_id is required for GCP secret listing")

        prefix = self._config.secret_prefix
        self._validate_secret_name(prefix)

        from google.cloud.secretmanager import SecretManagerServiceClient

        client = SecretManagerServiceClient()
        parent = f"projects/{self._config.project_id}"

        keys: list[str] = []
        for secret in client.list_secrets(request={"parent": parent, "filter": f"name:{prefix}"}):
            secret_id = secret.name.split("/")[-1]
            if secret_id.startswith(prefix):
                keys.append(secret_id[len(prefix) :])
        return sorted(keys)

    def delete(self, key: str) -> None:
        if not self._config.project_id:
            raise ValueError("project_id is required for GCP secret deletion")

        secret_name = self._secret_name(key)

        from google.api_core.exceptions import NotFound
        from google.cloud.secretmanager import SecretManagerServiceClient

        client = SecretManagerServiceClient()
        secret_path = f"projects/{self._config.project_id}/secrets/{secret_name}"
        try:
            client.delete_secret(request={"name": secret_path})
        except NotFound:
            raise KeyError(key)


class AWSSecretsBackend(SecretsBackend):
    """AWS Secrets Manager backend.

    Ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html
    """

    def upload(self, env_file: Path) -> dict[str, str]:
        env_vars = filter_secrets(parse_env_file(env_file))
        if not env_vars:
            return {}
        secret_entries = self._secret_entries(env_vars)

        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)
        results: dict[str, str] = {}

        for secret_id, value in secret_entries:
            try:
                client.put_secret_value(SecretId=secret_id, SecretString=value)
                results[secret_id] = "updated"
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                    client.create_secret(Name=secret_id, SecretString=value)
                    results[secret_id] = "created"
                else:
                    raise

        return results

    def list(self) -> list[str]:
        prefix = self._config.secret_prefix
        self._validate_secret_name(prefix)

        import boto3  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)

        paginator = client.get_paginator("list_secrets")
        keys: list[str] = []
        for page in paginator.paginate(Filters=[{"Key": "name", "Values": [prefix]}]):
            for secret_meta in page.get("SecretList", []):
                name = secret_meta["Name"]
                if name.startswith(prefix):
                    keys.append(name[len(prefix) :])
        return sorted(keys)

    def delete(self, key: str) -> None:
        secret_name = self._secret_name(key)

        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)
        try:
            client.delete_secret(SecretId=secret_name, ForceDeleteWithoutRecovery=True)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                raise KeyError(key)
            raise


def get_secrets_backend(config: DeploymentConfig) -> SecretsBackend:
    """Return the appropriate SecretsBackend for *config.cloud*."""
    if config.cloud == "gcp":
        return GCPSecretsBackend(config)
    return AWSSecretsBackend(config)
