"""Unit tests for deployment artifact generator."""

import pytest

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import generate_artifacts, list_generated_files


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GCP_CONFIG = DeploymentConfig(
    connector_name="my_salesforce",
    connector_class="MySalesforceConnector",
    connector_module="connectors.salesforce",
    cloud="gcp",
    region="us-central1",
    cluster_name="my-cluster",
    project_id="my-project",
    artifact_registry_repo="us-central1-docker.pkg.dev/my-project/connectors",
)

AWS_CONFIG = DeploymentConfig(
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
# GCP artifact completeness
# ---------------------------------------------------------------------------


def test_gcp_generates_all_expected_files():
    artifacts = generate_artifacts(GCP_CONFIG)
    expected = {
        "Dockerfile",
        "run.py",
        "terraform/main.tf",
        "terraform/variables.tf",
        "glean_deployment.yaml",
        ".env.example",
    }
    assert set(artifacts.keys()) == expected


def test_gcp_dockerfile_has_secret_manager():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "google-cloud-secret-manager" in artifacts["Dockerfile"]


def test_gcp_dockerfile_has_reference_link():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "https://cloud.google.com/artifact-registry/docs" in artifacts["Dockerfile"]
    assert "https://cloud.google.com/secret-manager/docs" in artifacts["Dockerfile"]


def test_gcp_terraform_has_reference_links():
    artifacts = generate_artifacts(GCP_CONFIG)
    tf = artifacts["terraform/main.tf"]
    assert "https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/" in tf
    assert "https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity" in tf
    assert "https://cloud.google.com/secret-manager/docs" in tf


def test_gcp_terraform_has_connector_name():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "my_salesforce" in artifacts["terraform/main.tf"]


def test_gcp_run_py_has_gcp_secret_manager():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "google.cloud" in artifacts["run.py"]
    assert "secretmanager" in artifacts["run.py"]


def test_gcp_run_py_has_reference_link():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "https://cloud.google.com/secret-manager/docs" in artifacts["run.py"]


# ---------------------------------------------------------------------------
# AWS artifact completeness
# ---------------------------------------------------------------------------


def test_aws_generates_all_expected_files():
    artifacts = generate_artifacts(AWS_CONFIG)
    expected = {
        "Dockerfile",
        "run.py",
        "terraform/main.tf",
        "terraform/variables.tf",
        "glean_deployment.yaml",
        ".env.example",
    }
    assert set(artifacts.keys()) == expected


def test_aws_dockerfile_has_boto3():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "boto3" in artifacts["Dockerfile"]


def test_aws_dockerfile_has_reference_link():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html" in artifacts["Dockerfile"]
    assert "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html" in artifacts["Dockerfile"]


def test_aws_terraform_has_reference_links():
    artifacts = generate_artifacts(AWS_CONFIG)
    tf = artifacts["terraform/main.tf"]
    assert "https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html" in tf
    assert "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html" in tf


def test_aws_run_py_has_boto3():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "boto3" in artifacts["run.py"]
    assert "secretsmanager" in artifacts["run.py"]


def test_aws_run_py_has_reference_link():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html" in artifacts["run.py"]


# ---------------------------------------------------------------------------
# .env.example
# ---------------------------------------------------------------------------


def test_env_example_has_redlist_vars():
    artifacts = generate_artifacts(GCP_CONFIG)
    env_ex = artifacts[".env.example"]
    assert "DATASOURCE_NAME" in env_ex
    assert "CLOUD_PLATFORM" in env_ex
    assert "INDEXING_MODE" in env_ex
    assert "GOOGLE_CLOUD_PROJECT" in env_ex


def test_aws_env_example_has_aws_region():
    artifacts = generate_artifacts(AWS_CONFIG)
    env_ex = artifacts[".env.example"]
    assert "AWS_REGION" in env_ex


def test_env_example_has_glean_creds():
    artifacts = generate_artifacts(GCP_CONFIG)
    env_ex = artifacts[".env.example"]
    assert "GLEAN_SERVER_URL" in env_ex
    assert "GLEAN_INDEXING_API_TOKEN" in env_ex


def test_env_example_has_secret_manager_reference_link():
    artifacts = generate_artifacts(GCP_CONFIG)
    env_ex = artifacts[".env.example"]
    assert "https://cloud.google.com/secret-manager/docs" in env_ex


def test_aws_env_example_has_secrets_manager_reference_link():
    artifacts = generate_artifacts(AWS_CONFIG)
    env_ex = artifacts[".env.example"]
    assert "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html" in env_ex


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_artifacts_are_deterministic():
    a1 = generate_artifacts(GCP_CONFIG)
    a2 = generate_artifacts(GCP_CONFIG)
    assert a1 == a2


def test_aws_artifacts_are_deterministic():
    a1 = generate_artifacts(AWS_CONFIG)
    a2 = generate_artifacts(AWS_CONFIG)
    assert a1 == a2


# ---------------------------------------------------------------------------
# Output to disk
# ---------------------------------------------------------------------------


def test_writes_files_to_disk(tmp_path):
    generate_artifacts(GCP_CONFIG, output_dir=tmp_path)

    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / "run.py").exists()
    assert (tmp_path / "terraform" / "main.tf").exists()
    assert (tmp_path / "terraform" / "variables.tf").exists()
    assert (tmp_path / "glean_deployment.yaml").exists()
    assert (tmp_path / ".env.example").exists()


def test_creates_output_dir_if_missing(tmp_path):
    out = tmp_path / "new_subdir"
    generate_artifacts(GCP_CONFIG, output_dir=out)
    assert out.exists()


# ---------------------------------------------------------------------------
# list_generated_files
# ---------------------------------------------------------------------------


def test_list_generated_files_gcp():
    files = list_generated_files("gcp")
    assert "Dockerfile" in files
    assert "run.py" in files
    assert "terraform/main.tf" in files
    assert "glean_deployment.yaml" in files
    assert ".env.example" in files


def test_list_generated_files_aws():
    files = list_generated_files("aws")
    assert "Dockerfile" in files
    assert "terraform/main.tf" in files


def test_list_generated_files_invalid_cloud_raises():
    with pytest.raises(ValueError, match="Unsupported cloud target"):
        list_generated_files("azure")
