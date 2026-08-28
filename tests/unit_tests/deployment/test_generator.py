"""Unit tests for deployment artifact generator."""

import os
import re
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
import yaml

from glean.api_client.models import CustomDatasourceConfig
from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from glean.indexing.deployment import generate_artifacts
from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import list_generated_files

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
        ".dockerignore",
    }
    assert set(artifacts.keys()) == expected


def test_generated_yaml_lists_the_complete_deployment_sequence():
    deployment_yaml = generate_artifacts(GCP_CONFIG)["glean_deployment.yaml"]

    assert deployment_yaml.index("datasource configure") < deployment_yaml.index(
        "deploy build --push"
    )
    assert deployment_yaml.index("deploy apply") < deployment_yaml.index("deploy run")


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


def test_gcp_terraform_reads_connector_name_at_apply_time():
    artifacts = generate_artifacts(GCP_CONFIG)
    assert "var.connector_name" in artifacts["terraform/main.tf"]
    assert 'variable "connector_name"' in artifacts["terraform/variables.tf"]


def test_gcp_terraform_uses_system_trust_for_explicit_dns_endpoint():
    terraform = generate_artifacts(GCP_CONFIG)["terraform/main.tf"]

    assert (
        "cluster_ca_certificate = var.cluster_endpoint == null ? "
        "base64decode(data.google_container_cluster.main.master_auth[0].cluster_ca_certificate) : null"
    ) in terraform


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
        ".dockerignore",
    }
    assert set(artifacts.keys()) == expected


def test_aws_dockerfile_has_boto3():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "boto3" in artifacts["Dockerfile"]


def test_aws_dockerfile_has_reference_link():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert (
        "https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html"
        in artifacts["Dockerfile"]
    )
    assert (
        "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html"
        in artifacts["Dockerfile"]
    )


def test_aws_terraform_has_reference_links():
    artifacts = generate_artifacts(AWS_CONFIG)
    tf = artifacts["terraform/main.tf"]
    assert (
        "https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html" in tf
    )
    assert "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html" in tf


def test_aws_run_py_has_boto3():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert "boto3" in artifacts["run.py"]
    assert "secretsmanager" in artifacts["run.py"]


def test_aws_run_py_has_reference_link():
    artifacts = generate_artifacts(AWS_CONFIG)
    assert (
        "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html"
        in artifacts["run.py"]
    )


def test_aws_generated_config_quotes_account_id():
    artifacts = generate_artifacts(AWS_CONFIG)

    assert 'account_id: "123456789012"' in artifacts["glean_deployment.yaml"]


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_generated_runner_uses_factory_for_connector_with_required_arguments(
    cloud, tmp_path, monkeypatch
):
    """Both cloud entrypoints use the same factory after provider secret loading."""
    calls = {}
    module_name = f"{cloud}_factory_connector"
    connector_module = ModuleType(module_name)

    class WikiDataClient(BaseDataClient[dict[str, str]]):
        def __init__(self, api_token):
            self.api_token = api_token

        def get_source_data(self, since=None, **kwargs):
            return []

    class CompanyWikiConnector(BaseDatasourceConnector[dict[str, str]]):
        configuration = CustomDatasourceConfig(name="my_salesforce", display_name="Salesforce")

        def transform(self, data):
            return []

        def index_data(self, mode, options=None):
            calls.update(
                connector=self.name,
                api_token=cast(WikiDataClient, self.data_client).api_token,
                mode=mode.value,
            )

    def create_connector():
        calls["factory_called"] = True
        return CompanyWikiConnector("my_salesforce", WikiDataClient(os.environ["SOURCE_API_TOKEN"]))

    setattr(connector_module, "CompanyWikiConnector", CompanyWikiConnector)
    setattr(connector_module, "create_connector", create_connector)
    monkeypatch.setitem(sys.modules, module_name, connector_module)

    if cloud == "aws":

        class FakeSecretsManager:
            def get_secret_value(self, *, SecretId):
                assert SecretId.endswith("SOURCE_API_TOKEN")
                return {"SecretString": "loaded-before-construction"}

        boto3 = ModuleType("boto3")
        setattr(boto3, "client", lambda *_args, **_kwargs: FakeSecretsManager())
        monkeypatch.setitem(sys.modules, "boto3", boto3)
        config = AWS_CONFIG
        provider_env = {"AWS_REGION": "us-east-1"}
    else:

        class FakeSecretManagerClient:
            def access_secret_version(self, *, request):
                assert request["name"].endswith("SOURCE_API_TOKEN/versions/latest")
                return SimpleNamespace(payload=SimpleNamespace(data=b"loaded-before-construction"))

        google = ModuleType("google")
        google.__path__ = []
        google_cloud = ModuleType("google.cloud")
        google_cloud.__path__ = []
        secretmanager = ModuleType("google.cloud.secretmanager")
        setattr(secretmanager, "SecretManagerServiceClient", FakeSecretManagerClient)
        setattr(google_cloud, "secretmanager", secretmanager)
        setattr(google, "cloud", google_cloud)
        monkeypatch.setitem(sys.modules, "google", google)
        monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
        monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", secretmanager)
        config = GCP_CONFIG
        provider_env = {"GOOGLE_CLOUD_PROJECT": "my-project"}

    config = config.model_copy(
        update={"connector_module": module_name, "connector_class": "CompanyWikiConnector"}
    )
    run_path = tmp_path / "run.py"
    run_path.write_text(generate_artifacts(config)["run.py"])
    environment = {
        "DATASOURCE_NAME": "my_salesforce",
        "CLOUD_PLATFORM": cloud,
        "INDEXING_MODE": "FULL",
        "SECRET_KEYS_JSON": '["SOURCE_API_TOKEN"]',
        "CONNECTOR_CLASS": "CompanyWikiConnector",
        "CONNECTOR_MODULE": module_name,
        "CONNECTOR_FACTORY": "create_connector",
        **provider_env,
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    runpy.run_path(str(run_path), run_name="__main__")

    assert calls == {
        "factory_called": True,
        "connector": "my_salesforce",
        "api_token": "loaded-before-construction",
        "mode": "full",
    }


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
@pytest.mark.parametrize("secret_keys_json", ['{"API_KEY": true}', '["BAD.KEY"]', "not-json"])
def test_generated_runner_rejects_malformed_secret_key_list(
    cloud, secret_keys_json, tmp_path, monkeypatch
):
    config = AWS_CONFIG if cloud == "aws" else GCP_CONFIG
    run_path = tmp_path / "run.py"
    run_path.write_text(generate_artifacts(config)["run.py"])
    environment = {
        "DATASOURCE_NAME": "my_salesforce",
        "CLOUD_PLATFORM": cloud,
        "INDEXING_MODE": "FULL",
        "SECRET_KEYS_JSON": secret_keys_json,
        "CONNECTOR_CLASS": "UnusedConnector",
        "CONNECTOR_MODULE": "unused_connector",
        "AWS_REGION" if cloud == "aws" else "GOOGLE_CLOUD_PROJECT": (
            "us-east-1" if cloud == "aws" else "my-project"
        ),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(run_path), run_name="__main__")

    assert excinfo.value.code == 1


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_generated_runner_exits_nonzero_when_declared_secret_load_fails(
    cloud, tmp_path, monkeypatch
):
    if cloud == "aws":

        class FailingSecretsManager:
            def get_secret_value(self, *, SecretId):
                raise RuntimeError(f"missing {SecretId}")

        boto3 = ModuleType("boto3")
        setattr(boto3, "client", lambda *_args, **_kwargs: FailingSecretsManager())
        monkeypatch.setitem(sys.modules, "boto3", boto3)
        config = AWS_CONFIG
        provider_env = {"AWS_REGION": "us-east-1"}
    else:

        class FailingSecretManagerClient:
            def access_secret_version(self, *, request):
                raise RuntimeError(f"missing {request['name']}")

        google = ModuleType("google")
        google.__path__ = []
        google_cloud = ModuleType("google.cloud")
        google_cloud.__path__ = []
        secretmanager = ModuleType("google.cloud.secretmanager")
        setattr(secretmanager, "SecretManagerServiceClient", FailingSecretManagerClient)
        setattr(google_cloud, "secretmanager", secretmanager)
        setattr(google, "cloud", google_cloud)
        monkeypatch.setitem(sys.modules, "google", google)
        monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
        monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", secretmanager)
        config = GCP_CONFIG
        provider_env = {"GOOGLE_CLOUD_PROJECT": "my-project"}

    run_path = tmp_path / "run.py"
    run_path.write_text(generate_artifacts(config)["run.py"])
    environment = {
        "DATASOURCE_NAME": "my_salesforce",
        "CLOUD_PLATFORM": cloud,
        "INDEXING_MODE": "FULL",
        "SECRET_KEYS_JSON": '["SOURCE_API_TOKEN"]',
        "CONNECTOR_CLASS": "UnusedConnector",
        "CONNECTOR_MODULE": "unused_connector",
        **provider_env,
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(run_path), run_name="__main__")

    assert excinfo.value.code == 1


def test_factory_identifier_is_quoted_in_generated_yaml():
    config = AWS_CONFIG.model_copy(update={"connector_factory": "null"})

    generated = generate_artifacts(config)["glean_deployment.yaml"]

    assert yaml.safe_load(generated)["connector_factory"] == "null"


@pytest.mark.parametrize("base_config", [AWS_CONFIG, GCP_CONFIG])
def test_factory_is_rendered_into_deployment_control_plane(base_config):
    config = base_config.model_copy(update={"connector_factory": "create_connector"})

    artifacts = generate_artifacts(config)

    assert yaml.safe_load(artifacts["glean_deployment.yaml"])["connector_factory"] == (
        "create_connector"
    )
    assert "CONNECTOR_FACTORY=create_connector" in artifacts[".env.example"]
    assert 'name  = "CONNECTOR_FACTORY"' in artifacts["terraform/main.tf"]
    assert (
        "for_each = var.connector_factory == null ? [] : [var.connector_factory]"
        in artifacts["terraform/main.tf"]
    )
    assert 'variable "connector_factory"' in artifacts["terraform/variables.tf"]


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
# Runtime user contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
def test_container_user_matches_kubernetes_security_context(config):
    artifacts = generate_artifacts(config)
    dockerfile = artifacts["Dockerfile"]
    terraform = artifacts["terraform/main.tf"]

    image_user = re.search(r"^USER ([0-9]+):([0-9]+)$", dockerfile, re.MULTILINE)
    run_as_user = re.search(r"run_as_user\s+=\s+([0-9]+)", terraform)
    run_as_group = re.search(r"run_as_group\s+=\s+([0-9]+)", terraform)

    assert image_user is not None
    assert run_as_user is not None
    assert run_as_group is not None
    assert image_user.groups() == (run_as_user.group(1), run_as_group.group(1))
    assert image_user.groups() == ("1000", "1000")


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


def test_disk_write_refuses_collision_and_preserves_exact_bytes(tmp_path):
    original = b"user-owned Dockerfile\n\xff\x00"
    (tmp_path / "Dockerfile").write_bytes(original)

    with pytest.raises(FileExistsError, match="Dockerfile"):
        generate_artifacts(GCP_CONFIG, output_dir=tmp_path)

    assert (tmp_path / "Dockerfile").read_bytes() == original
    assert not (tmp_path / "run.py").exists()
    assert not (tmp_path / ".gitignore").exists()


def test_disk_write_force_overwrites_with_exact_rendered_bytes(tmp_path):
    (tmp_path / "Dockerfile").write_bytes(b"user-owned Dockerfile\n")

    artifacts = generate_artifacts(GCP_CONFIG, output_dir=tmp_path, force=True)

    assert (tmp_path / "Dockerfile").read_bytes() == artifacts["Dockerfile"].encode("utf-8")
    assert (tmp_path / "run.py").read_bytes() == artifacts["run.py"].encode("utf-8")


def test_disk_write_gitignore_protection_is_idempotent(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_bytes(b"build/")

    generate_artifacts(GCP_CONFIG, output_dir=tmp_path)
    merged = gitignore.read_bytes()
    generate_artifacts(GCP_CONFIG, output_dir=tmp_path, force=True)

    assert gitignore.read_bytes() == merged
    assert merged == b"build/\n.env\n.terraform/\n*.tfstate*\n"


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


# ---------------------------------------------------------------------------
# Exact secret access from the deploy-time key manifest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
def test_terraform_accepts_secret_keys_json_and_passes_it_to_cronjob(config):
    artifacts = generate_artifacts(config)

    assert 'variable "secret_keys_json"' in artifacts["terraform/variables.tf"]
    assert "jsondecode(var.secret_keys_json)" in artifacts["terraform/main.tf"]
    assert 'name  = "SECRET_KEYS_JSON"' in artifacts["terraform/main.tf"]
    assert "value = var.secret_keys_json" in artifacts["terraform/main.tf"]


def test_gcp_terraform_grants_accessor_on_each_exact_derived_secret():
    tf = generate_artifacts(GCP_CONFIG)["terraform/main.tf"]

    assert 'resource "google_secret_manager_secret_iam_member" "secret_accessor"' in tf
    assert "for_each  = local.secret_names" in tf
    assert "secret_id = each.value" in tf
    assert '"${var.secret_prefix}${key}"' in tf
    assert "roles/secretmanager.secretAccessor" in tf
    assert 'google_project_iam_member" "secret_accessor' not in tf
    assert "resource.name.startsWith" not in tf
    assert "secretmanager.viewer" not in tf


def test_aws_terraform_resolves_exact_secret_arns_for_get_only():
    tf = generate_artifacts(AWS_CONFIG)["terraform/main.tf"]

    assert 'data "aws_secretsmanager_secret" "connector"' in tf
    assert "for_each = local.secret_names" in tf
    assert "name     = each.value" in tf
    assert "Resource = [for secret in data.aws_secretsmanager_secret.connector : secret.arn]" in tf
    assert 'Action   = ["secretsmanager:GetSecretValue"]' in tf
    assert "count = length(local.secret_names) == 0 ? 0 : 1" in tf
    assert "ListSecrets" not in tf
    assert "DescribeSecret" not in tf
    assert f"{AWS_CONFIG.secret_prefix}*" not in tf


def test_exact_secret_derivation_does_not_grant_connector_prefix_collision():
    tf = generate_artifacts(GCP_CONFIG)["terraform/main.tf"]
    colliding_connector_prefix = f"{GCP_CONFIG.secret_prefix.removesuffix('_')}_EXTRA_"

    assert colliding_connector_prefix not in tf
    assert "startsWith" not in tf
    assert "secret_id = each.value" in tf


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
def test_runner_uses_keys_json_for_direct_access_without_enumeration(config):
    run_py = generate_artifacts(config)["run.py"]

    assert "SECRET_KEYS_JSON" in run_py
    assert ".glean_secret_keys" not in run_py
    assert "list_secrets" not in run_py
    assert "get_paginator" not in run_py
    if config.cloud == "gcp":
        assert "access_secret_version" in run_py
    else:
        assert "get_secret_value" in run_py


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
def test_dockerignore_excludes_local_secret_manifest(config):
    assert ".glean_secret_keys" in generate_artifacts(config)[".dockerignore"].splitlines()


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
@pytest.mark.parametrize(
    "entry",
    [
        ".venv/",
        "venv/",
        ".pytest_cache/",
        ".tox/",
        ".nox/",
        ".coverage",
        ".coverage.*",
        "htmlcov/",
        "build/",
        "dist/",
        "*.egg-info/",
    ],
)
def test_dockerignore_excludes_python_development_artifacts(config, entry):
    assert entry in generate_artifacts(config)[".dockerignore"].splitlines()


@pytest.mark.parametrize("config", [AWS_CONFIG, GCP_CONFIG])
def test_terraform_requires_an_existing_customer_managed_namespace(config):
    terraform = generate_artifacts(config)["terraform/main.tf"]

    assert 'data "kubernetes_namespace_v1" "target"' in terraform
    assert 'resource "kubernetes_namespace_v1"' not in terraform
    assert "namespace = data.kubernetes_namespace_v1.target.metadata[0].name" in terraform
