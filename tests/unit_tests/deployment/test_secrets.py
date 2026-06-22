"""Unit tests for glean-deploy secrets module."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.secrets import (
    _REDLIST,
    filter_secrets,
    make_secret_name,
    parse_env_file,
    upload_secrets,
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


# ---------------------------------------------------------------------------
# make_secret_name
# ---------------------------------------------------------------------------


def test_make_secret_name_gcp(gcp_config):
    name = make_secret_name(gcp_config, "API_KEY")
    assert name == "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY"


def test_make_secret_name_aws(aws_config):
    name = make_secret_name(aws_config, "OAUTH_TOKEN")
    assert name == "CUSTOM_DATASOURCE_PLATFORM_MY_JIRA_OAUTH_TOKEN"


# ---------------------------------------------------------------------------
# upload_secrets dispatch
# ---------------------------------------------------------------------------


def test_upload_secrets_dispatches_to_gcp(gcp_config, env_file):
    with patch("glean.indexing.deployment.secrets.upload_secrets_gcp") as mock_gcp:
        mock_gcp.return_value = {"CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "created"}
        result = upload_secrets(gcp_config, env_file)
        mock_gcp.assert_called_once_with(gcp_config, env_file)
        assert "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY" in result


def test_upload_secrets_dispatches_to_aws(aws_config, env_file):
    with patch("glean.indexing.deployment.secrets.upload_secrets_aws") as mock_aws:
        mock_aws.return_value = {}
        upload_secrets(aws_config, env_file)
        mock_aws.assert_called_once_with(aws_config, env_file)


def test_upload_secrets_gcp_calls_secret_manager(gcp_config, env_file):
    mock_client = MagicMock()
    mock_client.get_secret.side_effect = Exception("not found")

    mock_sm_module = MagicMock()
    mock_sm_module.SecretManagerServiceClient.return_value = mock_client

    with patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm_module, "google.cloud": MagicMock()}):
        from glean.indexing.deployment.secrets import upload_secrets_gcp

        result = upload_secrets_gcp(gcp_config, env_file)

    # Both API_KEY and OAUTH_TOKEN should be returned
    assert len(result) == 2
    for v in result.values():
        assert v == "created"


def test_upload_secrets_aws_creates_new_secret(aws_config, env_file):
    # Build a fake ClientError without importing botocore directly.
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

    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore": mock_botocore, "botocore.exceptions": mock_botocore.exceptions}):
        from glean.indexing.deployment import secrets as secrets_mod
        import importlib
        importlib.reload(secrets_mod)
        result = secrets_mod.upload_secrets_aws(aws_config, env_file)

    assert len(result) == 2
    for v in result.values():
        assert v == "created"


def test_upload_secrets_empty_env_file_no_calls(gcp_config, tmp_path):
    empty_env = tmp_path / ".env"
    empty_env.write_text("")

    with patch("glean.indexing.deployment.secrets.upload_secrets_gcp") as mock_gcp:
        mock_gcp.return_value = {}
        result = upload_secrets(gcp_config, empty_env)
        assert result == {}
