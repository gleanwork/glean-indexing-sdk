"""Cloud secret manager backends for glean-deploy.

Each cloud platform has a dedicated backend class (GCPSecretsBackend,
AWSSecretsBackend) sharing a common SecretsBackend interface. Use
get_secrets_backend(config) to obtain the right one at runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

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
        "CONNECTOR_CLASS",
        "CONNECTOR_MODULE",
    ]
)


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

    def __init__(self, config: "DeploymentConfig") -> None:
        self._config = config

    def _secret_name(self, env_key: str) -> str:
        """Build the full cloud secret name: CUSTOM_DATASOURCE_PLATFORM_<NAME>_<KEY>."""
        return f"{self._config.secret_prefix}{env_key}"

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
    """GCP Secret Manager backend.

    Ref: https://cloud.google.com/secret-manager/docs
    """

    def upload(self, env_file: Path) -> dict[str, str]:
        if not self._config.project_id:
            raise ValueError("project_id is required for GCP secret upload")

        env_vars = filter_secrets(parse_env_file(env_file))
        if not env_vars:
            return {}

        from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]
        from google.cloud import secretmanager  # type: ignore[import-untyped]

        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{self._config.project_id}"
        results: dict[str, str] = {}

        for key, value in env_vars.items():
            secret_id = self._secret_name(key)
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

        from google.cloud import secretmanager  # type: ignore[import-untyped]

        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{self._config.project_id}"
        prefix = self._config.secret_prefix

        keys: list[str] = []
        for secret in client.list_secrets(request={"parent": parent, "filter": f"name:{prefix}"}):
            secret_id = secret.name.split("/")[-1]
            if secret_id.startswith(prefix):
                keys.append(secret_id[len(prefix):])
        return sorted(keys)

    def delete(self, key: str) -> None:
        if not self._config.project_id:
            raise ValueError("project_id is required for GCP secret deletion")

        from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]
        from google.cloud import secretmanager  # type: ignore[import-untyped]

        client = secretmanager.SecretManagerServiceClient()
        secret_path = f"projects/{self._config.project_id}/secrets/{self._secret_name(key)}"
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

        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)
        results: dict[str, str] = {}

        for key, value in env_vars.items():
            secret_id = self._secret_name(key)
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
        import boto3  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)
        prefix = self._config.secret_prefix

        paginator = client.get_paginator("list_secrets")
        keys: list[str] = []
        for page in paginator.paginate(Filters=[{"Key": "name", "Values": [prefix]}]):
            for secret_meta in page.get("SecretList", []):
                name = secret_meta["Name"]
                if name.startswith(prefix):
                    keys.append(name[len(prefix):])
        return sorted(keys)

    def delete(self, key: str) -> None:
        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=self._config.region)
        try:
            client.delete_secret(SecretId=self._secret_name(key), ForceDeleteWithoutRecovery=True)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                raise KeyError(key)
            raise


def get_secrets_backend(config: "DeploymentConfig") -> SecretsBackend:
    """Return the appropriate SecretsBackend for *config.cloud*."""
    if config.cloud == "gcp":
        return GCPSecretsBackend(config)
    return AWSSecretsBackend(config)
