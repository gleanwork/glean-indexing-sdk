"""Secrets upload for glean-deploy — GCP Secret Manager and AWS Secrets Manager."""

from __future__ import annotations

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


def make_secret_name(config: "DeploymentConfig", env_key: str) -> str:
    """Build the cloud secret name: CUSTOM_DATASOURCE_PLATFORM_<NAME>_<KEY>."""
    return f"{config.secret_prefix}{env_key}"


def upload_secrets_gcp(config: "DeploymentConfig", env_file: Path) -> dict[str, str]:
    """Upload connector secrets from a .env file to GCP Secret Manager.

    Idempotent: updates existing secrets, creates missing ones.
    Ref: https://cloud.google.com/secret-manager/docs
    """
    if not config.project_id:
        raise ValueError("project_id is required for GCP secret upload")

    env_vars = filter_secrets(parse_env_file(env_file))
    if not env_vars:
        return {}

    from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]
    from google.cloud import secretmanager  # type: ignore[import-untyped]

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{config.project_id}"
    results: dict[str, str] = {}

    for key, value in env_vars.items():
        secret_id = make_secret_name(config, key)
        secret_name = f"{parent}/secrets/{secret_id}"
        payload = value.encode("utf-8")

        # Check if the secret already exists.
        secret_existed = True
        try:
            client.get_secret(request={"name": secret_name})
        except NotFound:
            secret_existed = False
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )

        # Add a new version with the current value.
        client.add_secret_version(
            request={
                "parent": secret_name,
                "payload": {"data": payload},
            }
        )
        results[secret_id] = "updated" if secret_existed else "created"

    return results


def upload_secrets_aws(config: "DeploymentConfig", env_file: Path) -> dict[str, str]:
    """Upload connector secrets from a .env file to AWS Secrets Manager.

    Idempotent: updates existing secrets, creates missing ones.
    Ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html
    """
    env_vars = filter_secrets(parse_env_file(env_file))
    if not env_vars:
        return {}

    import boto3  # type: ignore[import-untyped]
    from botocore.exceptions import ClientError  # type: ignore[import-untyped]

    client = boto3.client("secretsmanager", region_name=config.region)
    results: dict[str, str] = {}

    for key, value in env_vars.items():
        secret_id = make_secret_name(config, key)
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


def upload_secrets(config: "DeploymentConfig", env_file: Path) -> dict[str, str]:
    """Upload connector secrets to GCP or AWS based on config.cloud."""
    if config.cloud == "gcp":
        return upload_secrets_gcp(config, env_file)
    return upload_secrets_aws(config, env_file)


def list_secrets_gcp(config: "DeploymentConfig") -> list[str]:
    """List all connector secrets in GCP Secret Manager matching the connector prefix.

    Returns the env-var key names (i.e. the part after the prefix).
    Ref: https://cloud.google.com/secret-manager/docs
    """
    if not config.project_id:
        raise ValueError("project_id is required for GCP secret listing")

    from google.cloud import secretmanager  # type: ignore[import-untyped]

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{config.project_id}"
    prefix = config.secret_prefix

    keys: list[str] = []
    for secret in client.list_secrets(request={"parent": parent, "filter": f"name:{prefix}"}):
        secret_id = secret.name.split("/")[-1]
        if secret_id.startswith(prefix):
            keys.append(secret_id[len(prefix):])
    return sorted(keys)


def list_secrets_aws(config: "DeploymentConfig") -> list[str]:
    """List all connector secrets in AWS Secrets Manager matching the connector prefix.

    Returns the env-var key names (i.e. the part after the prefix).
    Ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html
    """
    import boto3  # type: ignore[import-untyped]

    client = boto3.client("secretsmanager", region_name=config.region)
    prefix = config.secret_prefix

    paginator = client.get_paginator("list_secrets")
    keys: list[str] = []
    for page in paginator.paginate(Filters=[{"Key": "name", "Values": [prefix]}]):
        for secret_meta in page.get("SecretList", []):
            name = secret_meta["Name"]
            if name.startswith(prefix):
                keys.append(name[len(prefix):])
    return sorted(keys)


def list_secrets(config: "DeploymentConfig") -> list[str]:
    """List connector secrets in GCP or AWS based on config.cloud."""
    if config.cloud == "gcp":
        return list_secrets_gcp(config)
    return list_secrets_aws(config)


def delete_secret_gcp(config: "DeploymentConfig", env_key: str) -> None:
    """Delete a single connector secret from GCP Secret Manager.

    Ref: https://cloud.google.com/secret-manager/docs
    """
    if not config.project_id:
        raise ValueError("project_id is required for GCP secret deletion")

    from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]
    from google.cloud import secretmanager  # type: ignore[import-untyped]

    client = secretmanager.SecretManagerServiceClient()
    secret_id = make_secret_name(config, env_key)
    secret_name = f"projects/{config.project_id}/secrets/{secret_id}"
    try:
        client.delete_secret(request={"name": secret_name})
    except NotFound:
        raise KeyError(env_key)


def delete_secret_aws(config: "DeploymentConfig", env_key: str) -> None:
    """Delete a single connector secret from AWS Secrets Manager.

    Ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html
    """
    import boto3  # type: ignore[import-untyped]
    from botocore.exceptions import ClientError  # type: ignore[import-untyped]

    client = boto3.client("secretsmanager", region_name=config.region)
    secret_id = make_secret_name(config, env_key)
    try:
        client.delete_secret(SecretId=secret_id, ForceDeleteWithoutRecovery=True)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            raise KeyError(env_key)
        raise


def delete_secret(config: "DeploymentConfig", env_key: str) -> None:
    """Delete a connector secret from GCP or AWS based on config.cloud.

    Raises KeyError if the secret does not exist.
    """
    if config.cloud == "gcp":
        return delete_secret_gcp(config, env_key)
    return delete_secret_aws(config, env_key)
