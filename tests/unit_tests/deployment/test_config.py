"""Unit tests for DeploymentConfig."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from glean.indexing.deployment.config import DeploymentConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GCP_KWARGS: dict[str, Any] = {
    "connector_name": "my_salesforce",
    "connector_class": "MySalesforceConnector",
    "connector_module": "connectors.salesforce",
    "cloud": "gcp",
    "region": "us-central1",
    "cluster_name": "my-cluster",
    "project_id": "my-project",
    "artifact_registry_repo": "us-central1-docker.pkg.dev/my-project/connectors",
}

AWS_KWARGS: dict[str, Any] = {
    "connector_name": "my_salesforce",
    "connector_class": "MySalesforceConnector",
    "connector_module": "connectors.salesforce",
    "cloud": "aws",
    "region": "us-east-1",
    "cluster_name": "my-eks-cluster",
    "account_id": "123456789012",
    "ecr_repo": "123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors",
}


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
    assert config.k8s_name == "my-connector"


@pytest.mark.parametrize("namespace", ["a", "0", "my-namespace", "a" * 63])
def test_namespace_accepts_ascii_kubernetes_dns_label_boundaries(namespace):
    config = DeploymentConfig(**{**AWS_KWARGS, "namespace": namespace})
    assert config.namespace == namespace


@pytest.mark.parametrize(
    "namespace",
    ["", "a" * 64, "-namespace", "namespace-", "my_namespace", "Default", "名前", "namespace\n"],
)
def test_namespace_rejects_invalid_kubernetes_dns_labels(namespace):
    with pytest.raises(ValidationError, match="namespace must be 1-63 ASCII"):
        DeploymentConfig(**{**AWS_KWARGS, "namespace": namespace})


# ---------------------------------------------------------------------------
# Resource name validation (#162)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("connector_name", ["demoé", "demo\n"])
def test_connector_name_requires_ascii_fullmatch(connector_name):
    with pytest.raises(ValidationError, match="connector_name must be lowercase"):
        DeploymentConfig(**{**AWS_KWARGS, "connector_name": connector_name})


@pytest.mark.parametrize("length", [1, 52])
def test_cronjob_name_accepts_length_boundaries(length):
    config = DeploymentConfig(**{**AWS_KWARGS, "connector_name": "a" * length})
    assert len(config.k8s_name) == length


def test_cronjob_name_rejects_53_characters():
    with pytest.raises(ValidationError, match="CronJob.*1-52"):
        DeploymentConfig(**{**AWS_KWARGS, "connector_name": "a" * 53})


def test_trailing_hyphen_k8s_name_raises():
    with pytest.raises(ValidationError, match="CronJob"):
        DeploymentConfig(**{**AWS_KWARGS, "connector_name": "demo-"})


@pytest.mark.parametrize("length", [3, 27])
def test_derived_gcp_service_account_accepts_6_and_30_characters(length):
    config = DeploymentConfig(**{**GCP_KWARGS, "connector_name": "a" * length})
    assert len(config.effective_service_account) in (6, 30)


@pytest.mark.parametrize("length", [2, 28])
def test_derived_gcp_service_account_rejects_outside_6_and_30(length):
    with pytest.raises(ValidationError, match="Derived GCP service account.*6-30"):
        DeploymentConfig(**{**GCP_KWARGS, "connector_name": "a" * length})


@pytest.mark.parametrize("length", [6, 30])
def test_explicit_gcp_service_account_accepts_length_boundaries(length):
    service_account_name = "a" * length
    config = DeploymentConfig(**{**GCP_KWARGS, "service_account_name": service_account_name})
    assert config.effective_service_account == service_account_name


@pytest.mark.parametrize(
    "service_account_name", ["a" * 5, "a" * 31, "1valid", "valid-", "válido", "valid\n"]
)
def test_invalid_explicit_gcp_service_account_names_identify_override(service_account_name):
    with pytest.raises(ValidationError, match="service_account_name.*invalid"):
        DeploymentConfig(**{**GCP_KWARGS, "service_account_name": service_account_name})


def test_gcp_explicit_service_account_overrides_invalid_derived_default():
    config = DeploymentConfig(
        **{**GCP_KWARGS, "connector_name": "hr", "service_account_name": "my-valid-sa"}
    )
    assert config.effective_service_account == "my-valid-sa"


@pytest.mark.parametrize("iam_role_name", ["a", "a" * 64, "Role_+=,.@-9"])
def test_explicit_aws_iam_role_accepts_boundaries_and_ascii_punctuation(iam_role_name):
    config = DeploymentConfig(**{**AWS_KWARGS, "iam_role_name": iam_role_name})
    assert config.effective_service_account == iam_role_name


@pytest.mark.parametrize("iam_role_name", ["a" * 65, "role/name", "rôle", "role\n"])
def test_invalid_explicit_aws_iam_role_names_identify_override(iam_role_name):
    with pytest.raises(ValidationError, match="iam_role_name.*invalid"):
        DeploymentConfig(**{**AWS_KWARGS, "iam_role_name": iam_role_name})


@pytest.mark.parametrize(
    ("cloud_kwargs", "repo_field", "base_path_length"),
    [
        (GCP_KWARGS, "artifact_registry_repo", 251),
        (AWS_KWARGS, "ecr_repo", 252),
    ],
)
def test_derived_image_repository_path_accepts_provider_length_boundary(
    cloud_kwargs, repo_field, base_path_length
):
    registry = cloud_kwargs[repo_field].split("/", maxsplit=1)[0]
    config = DeploymentConfig(
        **{
            **cloud_kwargs,
            "connector_name": "app",
            repo_field: f"{registry}/{'a' * base_path_length}",
        }
    )
    assert config.image_name.endswith("/app")


@pytest.mark.parametrize(
    ("cloud_kwargs", "repo_field", "base_path_length", "error"),
    [
        (GCP_KWARGS, "artifact_registry_repo", 252, "Artifact Registry"),
        (AWS_KWARGS, "ecr_repo", 253, "ECR"),
    ],
)
def test_derived_image_repository_path_rejects_over_provider_length(
    cloud_kwargs, repo_field, base_path_length, error
):
    registry = cloud_kwargs[repo_field].split("/", maxsplit=1)[0]
    with pytest.raises(ValidationError, match=error):
        DeploymentConfig(
            **{
                **cloud_kwargs,
                "connector_name": "app",
                repo_field: f"{registry}/{'a' * base_path_length}",
            }
        )


def test_aws_ecr_repository_path_accepts_two_character_minimum():
    config = DeploymentConfig(
        **{**AWS_KWARGS, "connector_name": "ab", "ecr_repo": "registry.example.com"}
    )
    assert config.image_name == "registry.example.com/ab"


def test_aws_ecr_repository_path_rejects_one_character():
    with pytest.raises(ValidationError, match="ECR.*2-256"):
        DeploymentConfig(
            **{**AWS_KWARGS, "connector_name": "a", "ecr_repo": "registry.example.com"}
        )


@pytest.mark.parametrize("repository_component", ["repo--name", "repo__name"])
def test_aws_ecr_repository_path_accepts_documented_repeated_separators(repository_component):
    config = DeploymentConfig(
        **{
            **AWS_KWARGS,
            "connector_name": "app",
            "ecr_repo": f"registry.example.com/{repository_component}",
        }
    )
    assert repository_component in config.image_name


@pytest.mark.parametrize(
    ("cloud_kwargs", "repo_field", "error"),
    [
        (GCP_KWARGS, "artifact_registry_repo", "Artifact Registry"),
        (AWS_KWARGS, "ecr_repo", "ECR"),
    ],
)
def test_derived_image_repository_rejects_invalid_component(cloud_kwargs, repo_field, error):
    with pytest.raises(ValidationError, match=error):
        DeploymentConfig(**{**cloud_kwargs, "connector_name": "my_-connector"})

    with pytest.raises(ValidationError, match=error):
        DeploymentConfig(
            **{
                **cloud_kwargs,
                "connector_name": "valid",
                repo_field: f"{cloud_kwargs[repo_field]}/",
            }
        )


@pytest.mark.parametrize(
    ("cloud_kwargs", "repo_field", "error"),
    [
        (GCP_KWARGS, "artifact_registry_repo", "Artifact Registry"),
        (AWS_KWARGS, "ecr_repo", "ECR"),
    ],
)
def test_repository_path_rejects_undocumented_angle_bracket_component(
    cloud_kwargs, repo_field, error
):
    registry = cloud_kwargs[repo_field].split("/", maxsplit=1)[0]
    with pytest.raises(ValidationError, match=error):
        DeploymentConfig(
            **{
                **cloud_kwargs,
                "connector_name": "app",
                repo_field: f"{registry}/<arbitrary-placeholder>",
            }
        )


def test_gcp_repository_path_accepts_documented_init_placeholder():
    config = DeploymentConfig(
        **{
            **GCP_KWARGS,
            "artifact_registry_repo": "<region>-docker.pkg.dev/<project>/connectors",
        }
    )
    assert config.artifact_registry_repo == "<region>-docker.pkg.dev/<project>/connectors"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_image_name_gcp():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.image_name == "us-central1-docker.pkg.dev/my-project/connectors/my_salesforce"


def test_image_name_aws():
    config = DeploymentConfig(**AWS_KWARGS)
    assert (
        config.image_name == "123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors/my_salesforce"
    )


def test_secret_prefix_uppercase():
    config = DeploymentConfig(**GCP_KWARGS)
    assert config.secret_prefix == "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_"


def test_effective_service_account_gcp_default():
    config = DeploymentConfig(**GCP_KWARGS)
    # k8s_name is used: underscores → hyphens
    assert config.effective_service_account == "my-salesforce-sa"


def test_effective_service_account_gcp_custom():
    config = DeploymentConfig(**{**GCP_KWARGS, "service_account_name": "custom-sa"})
    assert config.effective_service_account == "custom-sa"


def test_effective_service_account_aws_default():
    config = DeploymentConfig(**AWS_KWARGS)
    # k8s_name is used: underscores → hyphens
    assert config.effective_service_account == "my-salesforce-role"


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
