"""Cloud secret manager backends for glean-deploy.

Each cloud platform has a dedicated backend class (GCPSecretsBackend,
AWSSecretsBackend) sharing a common SecretsBackend interface. Use
get_secrets_backend(config) to obtain the right one at runtime.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from glean.indexing.recipes.pull.auth import OAuth2Token, OAuth2TokenError

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

OAUTH_TOKEN_STATE_ENV_VAR = "SOURCE_OAUTH_TOKEN_STATE"


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
                keys.append(secret_id[len(prefix) :])
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
                    keys.append(name[len(prefix) :])
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


class GCPOAuth2TokenStore:
    """Persist OAuth2 token state in a pre-created GCP secret."""

    def __init__(self, *, project_id: str, connector_name: str, client: Any | None = None) -> None:
        self._secret_path = (
            f"projects/{project_id}/secrets/"
            f"CUSTOM_DATASOURCE_PLATFORM_{connector_name.upper()}_{OAUTH_TOKEN_STATE_ENV_VAR}"
        )
        self._client = client

    def load(self) -> OAuth2Token:
        """Load the latest OAuth2 token state."""
        client = self._get_client()
        try:
            response = client.access_secret_version(
                request={"name": f"{self._secret_path}/versions/latest"}
            )
            return _deserialize_oauth2_token(response.payload.data.decode("utf-8"))
        except OAuth2TokenError:
            raise
        except Exception as exc:
            raise OAuth2TokenError(
                "Could not load OAuth2 token state from GCP Secret Manager"
            ) from exc

    def save(self, token: OAuth2Token) -> None:
        """Add a GCP secret version containing the refreshed token state."""
        try:
            self._get_client().add_secret_version(
                request={
                    "parent": self._secret_path,
                    "payload": {"data": _serialize_oauth2_token(token).encode("utf-8")},
                }
            )
        except Exception as exc:
            raise OAuth2TokenError(
                "Could not save OAuth2 token state to GCP Secret Manager"
            ) from exc

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import secretmanager  # type: ignore[import-untyped]

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client


class AWSOAuth2TokenStore:
    """Persist OAuth2 token state in a pre-created AWS secret."""

    def __init__(
        self,
        *,
        region: str,
        connector_name: str,
        client: Any | None = None,
    ) -> None:
        self._region = region
        self._secret_name = (
            f"CUSTOM_DATASOURCE_PLATFORM_{connector_name.upper()}_{OAUTH_TOKEN_STATE_ENV_VAR}"
        )
        self._client = client

    def load(self) -> OAuth2Token:
        """Load the latest OAuth2 token state."""
        try:
            response = self._get_client().get_secret_value(SecretId=self._secret_name)
            return _deserialize_oauth2_token(response["SecretString"])
        except OAuth2TokenError:
            raise
        except Exception as exc:
            raise OAuth2TokenError(
                "Could not load OAuth2 token state from AWS Secrets Manager"
            ) from exc

    def save(self, token: OAuth2Token) -> None:
        """Replace the AWS secret value with the refreshed token state."""
        try:
            self._get_client().put_secret_value(
                SecretId=self._secret_name,
                SecretString=_serialize_oauth2_token(token),
            )
        except Exception as exc:
            raise OAuth2TokenError(
                "Could not save OAuth2 token state to AWS Secrets Manager"
            ) from exc

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # type: ignore[import-untyped]

            self._client = boto3.client("secretsmanager", region_name=self._region)
        return self._client


def get_oauth2_token_store_from_environment(
    environ: Mapping[str, str] | None = None,
) -> GCPOAuth2TokenStore | AWSOAuth2TokenStore:
    """Create the cloud token store configured by deployment environment variables."""
    values = os.environ if environ is None else environ
    cloud = _required_environment_value(values, "CLOUD_PLATFORM").lower()
    connector_name = _required_environment_value(values, "DATASOURCE_NAME")

    if cloud == "gcp":
        return GCPOAuth2TokenStore(
            project_id=_required_environment_value(values, "GOOGLE_CLOUD_PROJECT"),
            connector_name=connector_name,
        )
    if cloud == "aws":
        return AWSOAuth2TokenStore(
            region=_required_environment_value(values, "AWS_REGION"),
            connector_name=connector_name,
        )
    raise OAuth2TokenError(f"Unsupported cloud platform for OAuth2 token storage: {cloud}")


def _required_environment_value(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not value:
        raise OAuth2TokenError(f"Missing required OAuth2 token store environment variable: {name}")
    return value


def _serialize_oauth2_token(token: OAuth2Token) -> str:
    return json.dumps(token.to_dict(), separators=(",", ":"), sort_keys=True)


def _deserialize_oauth2_token(value: str) -> OAuth2Token:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OAuth2TokenError("Stored OAuth2 token state is not valid JSON") from exc
    if not isinstance(data, Mapping):
        raise OAuth2TokenError("Stored OAuth2 token state must be a JSON object")
    return OAuth2Token.from_dict(data)


def get_secrets_backend(config: "DeploymentConfig") -> SecretsBackend:
    """Return the appropriate SecretsBackend for *config.cloud*."""
    if config.cloud == "gcp":
        return GCPSecretsBackend(config)
    return AWSSecretsBackend(config)
