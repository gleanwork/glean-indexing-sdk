"""Unit tests for glean-deploy secrets module."""

from unittest.mock import MagicMock, patch

import pytest

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.secrets import (
    _REDLIST,
    AWSSecretsBackend,
    GCPSecretsBackend,
    filter_secrets,
    get_secrets_backend,
    parse_env_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gcp_config():
    return DeploymentConfig(
        connector_name="my_salesforce",
        connector_class="MySalesforceConnector",
        connector_module="connectors.salesforce",
        cloud="gcp",
        region="us-central1",
        cluster_name="my-cluster",
        project_id="my-project",
        artifact_registry_repo="us-central1-docker.pkg.dev/my-project/connectors",
    )


@pytest.fixture()
def aws_config():
    return DeploymentConfig(
        connector_name="my_jira",
        connector_class="MyJiraConnector",
        connector_module="connectors.jira",
        cloud="aws",
        region="us-east-1",
        cluster_name="my-eks-cluster",
        account_id="123456789012",
        ecr_repo="123456789012.dkr.ecr.us-east-1.amazonaws.com/connectors",
    )


@pytest.fixture()
def env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("API_KEY=secret123\nOAUTH_TOKEN=token456\n")
    return f


@pytest.fixture()
def env_file_with_redlist(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "API_KEY=secret123\n"
        "GOOGLE_CLOUD_PROJECT=my-project\n"
        "DATASOURCE_NAME=salesforce\n"
        "CONNECTOR_CLASS=MySalesforceConnector\n"
    )
    return f


# ---------------------------------------------------------------------------
# parse_env_file
# ---------------------------------------------------------------------------


def test_parse_env_file_basic(env_file):
    result = parse_env_file(env_file)
    assert result == {"API_KEY": "secret123", "OAUTH_TOKEN": "token456"}


def test_parse_env_file_empty(tmp_path):
    f = tmp_path / ".env"
    f.write_text("")
    result = parse_env_file(f)
    assert result == {}


def test_parse_env_file_ignores_comments(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# this is a comment\nAPI_KEY=abc\n")
    result = parse_env_file(f)
    assert "API_KEY" in result
    assert len(result) == 1


def test_parse_env_file_strips_blank_lines(tmp_path):
    f = tmp_path / ".env"
    f.write_text("\n\nAPI_KEY=abc\n\n")
    result = parse_env_file(f)
    assert result == {"API_KEY": "abc"}


# ---------------------------------------------------------------------------
# filter_secrets
# ---------------------------------------------------------------------------


def test_filter_secrets_removes_redlist():
    env_vars = {
        "API_KEY": "secret",
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "DATASOURCE_NAME": "salesforce",
        "CONNECTOR_CLASS": "MyConnector",
    }
    result = filter_secrets(env_vars)
    assert "API_KEY" in result
    assert "GOOGLE_CLOUD_PROJECT" not in result
    assert "DATASOURCE_NAME" not in result
    assert "CONNECTOR_CLASS" not in result


def test_filter_secrets_keeps_non_redlist():
    env_vars = {"API_KEY": "secret123", "OAUTH_TOKEN": "tok456"}
    result = filter_secrets(env_vars)
    assert result == {"API_KEY": "secret123", "OAUTH_TOKEN": "tok456"}


def test_filter_secrets_empty_dict():
    assert filter_secrets({}) == {}


def test_redlist_contains_expected_vars():
    assert "GOOGLE_CLOUD_PROJECT" in _REDLIST
    assert "AWS_REGION" in _REDLIST
    assert "DATASOURCE_NAME" in _REDLIST
    assert "CLOUD_PLATFORM" in _REDLIST
    assert "INDEXING_MODE" in _REDLIST
    assert "CONNECTOR_CLASS" in _REDLIST
    assert "CONNECTOR_MODULE" in _REDLIST


def test_redlist_covers_all_template_deployment_env_vars():
    """Trip-wire: every static env var name in the Terraform templates must be in _REDLIST.

    If this test fails, a deployment-control env var was added to a template without
    a corresponding _REDLIST entry, meaning it would be silently uploaded as a secret.
    """
    import re
    from pathlib import Path

    templates_dir = (
        Path(__file__).parents[3] / "src" / "glean" / "indexing" / "deployment" / "templates"
    )
    # Matches:  name  = "UPPER_CASE_VAR"  (only uppercase — Terraform interpolations like ${...} are excluded)
    pattern = re.compile(r'name\s+=\s+"([A-Z][A-Z0-9_]+)"')

    template_env_vars: set[str] = set()
    for tf_template in templates_dir.rglob("*.tf.j2"):
        for match in pattern.finditer(tf_template.read_text()):
            template_env_vars.add(match.group(1))

    missing = template_env_vars - _REDLIST
    assert not missing, (
        f"Deployment env vars in templates but missing from _REDLIST: {sorted(missing)}. "
        "Add them to _REDLIST in secrets.py or they will be uploaded as connector secrets."
    )


# ---------------------------------------------------------------------------
# _secret_name (SecretsBackend method)
# ---------------------------------------------------------------------------


def test_secret_name_gcp(gcp_config):
    backend = GCPSecretsBackend(gcp_config)
    name = backend._secret_name("API_KEY")
    assert name == "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY"


def test_secret_name_aws(aws_config):
    backend = AWSSecretsBackend(aws_config)
    name = backend._secret_name("OAUTH_TOKEN")
    assert name == "CUSTOM_DATASOURCE_PLATFORM_MY_JIRA_OAUTH_TOKEN"


# ---------------------------------------------------------------------------
# get_secrets_backend dispatch
# ---------------------------------------------------------------------------


def test_get_secrets_backend_gcp(gcp_config):
    backend = get_secrets_backend(gcp_config)
    assert isinstance(backend, GCPSecretsBackend)


def test_get_secrets_backend_aws(aws_config):
    backend = get_secrets_backend(aws_config)
    assert isinstance(backend, AWSSecretsBackend)


# ---------------------------------------------------------------------------
# GCPSecretsBackend.upload
# ---------------------------------------------------------------------------


def test_gcp_upload_creates_new_secrets(gcp_config, env_file):
    class _FakeNotFound(Exception):
        pass

    mock_client = MagicMock()
    mock_client.get_secret.side_effect = _FakeNotFound("not found")

    mock_sm_module = MagicMock()
    mock_sm_module.SecretManagerServiceClient.return_value = mock_client

    mock_google_cloud = MagicMock()
    mock_google_cloud.secretmanager = mock_sm_module

    mock_api_core_exc = MagicMock()
    mock_api_core_exc.NotFound = _FakeNotFound

    with patch.dict(
        "sys.modules",
        {
            "google": MagicMock(),
            "google.cloud": mock_google_cloud,
            "google.cloud.secretmanager": mock_sm_module,
            "google.api_core": MagicMock(),
            "google.api_core.exceptions": mock_api_core_exc,
        },
    ):
        import importlib

        from glean.indexing.deployment import secrets as secrets_mod

        importlib.reload(secrets_mod)
        backend = secrets_mod.GCPSecretsBackend(gcp_config)
        result = backend.upload(env_file)

    assert len(result) == 2
    for v in result.values():
        assert v == "created"


def test_gcp_upload_returns_updated_for_existing_secrets(gcp_config, env_file):
    class _FakeNotFound(Exception):
        pass

    mock_client = MagicMock()
    mock_client.get_secret.return_value = MagicMock()  # no exception → exists

    mock_sm_module = MagicMock()
    mock_sm_module.SecretManagerServiceClient.return_value = mock_client

    mock_google_cloud = MagicMock()
    mock_google_cloud.secretmanager = mock_sm_module

    mock_api_core_exc = MagicMock()
    mock_api_core_exc.NotFound = _FakeNotFound

    with patch.dict(
        "sys.modules",
        {
            "google": MagicMock(),
            "google.cloud": mock_google_cloud,
            "google.cloud.secretmanager": mock_sm_module,
            "google.api_core": MagicMock(),
            "google.api_core.exceptions": mock_api_core_exc,
        },
    ):
        import importlib

        from glean.indexing.deployment import secrets as secrets_mod

        importlib.reload(secrets_mod)
        backend = secrets_mod.GCPSecretsBackend(gcp_config)
        result = backend.upload(env_file)

    assert len(result) == 2
    for v in result.values():
        assert v == "updated"


def test_gcp_upload_empty_env_returns_early(gcp_config, tmp_path):
    """GCP upload returns empty dict without importing GCP SDK when no secrets."""
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    backend = GCPSecretsBackend(gcp_config)
    result = backend.upload(empty_env)
    assert result == {}


# ---------------------------------------------------------------------------
# AWSSecretsBackend.upload
# ---------------------------------------------------------------------------


def test_aws_upload_creates_new_secret(aws_config, env_file):
    class _FakeClientError(Exception):
        def __init__(self, response, operation_name):
            self.response = response
            self.operation_name = operation_name

    mock_botocore = MagicMock()
    mock_botocore.exceptions.ClientError = _FakeClientError

    mock_client = MagicMock()
    error_response = {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}}
    mock_client.put_secret_value.side_effect = _FakeClientError(error_response, "PutSecretValue")

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict(
        "sys.modules",
        {
            "boto3": mock_boto3,
            "botocore": mock_botocore,
            "botocore.exceptions": mock_botocore.exceptions,
        },
    ):
        import importlib

        from glean.indexing.deployment import secrets as secrets_mod

        importlib.reload(secrets_mod)
        backend = secrets_mod.AWSSecretsBackend(aws_config)
        result = backend.upload(env_file)

    assert len(result) == 2
    for v in result.values():
        assert v == "created"


def test_aws_upload_empty_env_returns_early(aws_config, tmp_path):
    """AWS upload returns empty dict without importing boto3 when no secrets."""
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    backend = AWSSecretsBackend(aws_config)
    result = backend.upload(empty_env)
    assert result == {}
