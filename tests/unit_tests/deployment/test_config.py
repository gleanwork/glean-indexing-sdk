"""Unit tests for DeploymentConfig."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from glean.indexing.deployment.config import DeploymentConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GCP_KWARGS = dict(
    connector_name="my_salesforce",
    connector_class="MySalesforceConnector",
    connector_module="connectors.salesforce",
    cloud="gcp",
    region="us-central1",
    cluster_name="my-cluster",
    project_id="my-project",
    artifact_registry_repo="us-central1-docker.pkg.dev/my-project/connectors",
)

AWS_KWARGS = dict(
    connector_name="my_salesforce",
    connector_class="MySalesforceConnector",
    connector_module="connectors.salesforce",
    cloud="aws",
    region="us-east-1",
    cluster_name="my-eks-cluster",
    account_id="123456789012",
    ecr_repo="123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors",
)


# ---------------------------------------------------------------------------
# Valid GCP config
# ---------------------------------------------------------------------------


def test_gcp_config_valid():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.connector_name == "my_salesforce"
    assert config.cloud == "gcp"
    assert config.project_id == "my-project"


def test_gcp_config_defaults():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.namespace == "default"
    assert config.cpu == "500m"
    assert config.memory == "512Mi"
    assert config.cron_schedule == "0 2 * * *"
    assert config.indexing_mode == "FULL"


# ---------------------------------------------------------------------------
# Valid AWS config
# ---------------------------------------------------------------------------


def test_aws_config_valid():
    config = DeploymentConfig(**AWS_KWARGS)
    assert config.cloud == "aws"
    assert config.account_id == "123456789012"
    assert config.ecr_repo == "123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_gcp_missing_project_id_raises():
    kwargs = {**GCP_KWARGS}
    del kwargs["project_id"]
    with pytest.raises(ValidationError, match="project_id is required"):
        DeploymentConfig(**kwargs)


def test_gcp_missing_registry_raises():
    kwargs = {**GCP_KWARGS}
    del kwargs["artifact_registry_repo"]
    with pytest.raises(ValidationError, match="artifact_registry_repo is required"):
        DeploymentConfig(**kwargs)


def test_aws_missing_account_id_raises():
    kwargs = {**AWS_KWARGS}
    del kwargs["account_id"]
    with pytest.raises(ValidationError, match="account_id is required"):
        DeploymentConfig(**kwargs)


def test_aws_missing_ecr_repo_raises():
    kwargs = {**AWS_KWARGS}
    del kwargs["ecr_repo"]
    with pytest.raises(ValidationError, match="ecr_repo is required"):
        DeploymentConfig(**kwargs)


def test_invalid_connector_name_raises():
    with pytest.raises(ValidationError, match="connector_name must be lowercase"):
        DeploymentConfig(**{**GCP_KWARGS, "connector_name": "MyConnector"})


def test_connector_name_with_hyphen_valid():
    config = DeploymentConfig(**{**GCP_KWARGS, "connector_name": "my-connector"})
    assert config.connector_name == "my-connector"


def test_connector_name_with_underscore_valid():
    config = DeploymentConfig(**{**GCP_KWARGS, "connector_name": "my_connector"})
    assert config.connector_name == "my_connector"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_image_name_gcp():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.image_name == "us-central1-docker.pkg.dev/my-project/connectors/my_salesforce"


def test_image_name_aws():
    config = DeploymentConfig(**AWS_KWARGS)
    assert config.image_name == "123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors/my_salesforce"


def test_secret_prefix_uppercase():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.secret_prefix == "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_"


def test_effective_service_account_gcp_default():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.effective_service_account == "my_salesforce-sa"


def test_effective_service_account_gcp_custom():
    config = DeploymentConfig(**{**GCP_KWARGS, "service_account_name": "custom-sa"})
    assert config.effective_service_account == "custom-sa"


def test_effective_service_account_aws_default():
    config = DeploymentConfig(**AWS_KWARGS)
    assert config.effective_service_account == "my_salesforce-role"


# ---------------------------------------------------------------------------
# YAML round-trip
# ---------------------------------------------------------------------------


def test_yaml_round_trip(tmp_path):
    config = DeploymentConfig(**GCP_KWARGS)
    yaml_path = tmp_path / "glean_deployment.yaml"
    config.to_yaml(yaml_path)

    loaded = DeploymentConfig.from_yaml(yaml_path)
    assert loaded.connector_name == config.connector_name
    assert loaded.cloud == config.cloud
    assert loaded.project_id == config.project_id
    assert loaded.artifact_registry_repo == config.artifact_registry_repo


def test_yaml_round_trip_aws(tmp_path):
    config = DeploymentConfig(**AWS_KWARGS)
    yaml_path = tmp_path / "glean_deployment.yaml"
    config.to_yaml(yaml_path)

    loaded = DeploymentConfig.from_yaml(yaml_path)
    assert loaded.connector_name == config.connector_name
    assert loaded.account_id == config.account_id


def test_from_yaml_file_not_found():
    with pytest.raises(FileNotFoundError):
        DeploymentConfig.from_yaml(Path("/nonexistent/glean_deployment.yaml"))


def test_yaml_excludes_none_fields(tmp_path):
    config = DeploymentConfig(**GCP_KWARGS)  # no AWS fields
    yaml_path = tmp_path / "glean_deployment.yaml"
    config.to_yaml(yaml_path)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assert "account_id" not in data
    assert "ecr_repo" not in data
