"""Unit tests for glean-deploy CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from glean.indexing.deployment.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def gcp_deployment_yaml(tmp_path):
    content = """
connector_name: my_salesforce
connector_class: MySalesforceConnector
connector_module: connectors.salesforce
cloud: gcp
region: us-central1
cluster_name: my-cluster
project_id: my-project
artifact_registry_repo: us-central1-docker.pkg.dev/my-project/connectors
cron_schedule: "0 2 * * *"
indexing_mode: FULL
"""
    yaml_file = tmp_path / "glean_deployment.yaml"
    yaml_file.write_text(content)
    return yaml_file


# ---------------------------------------------------------------------------
# Help / top-level
# ---------------------------------------------------------------------------


def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "glean-deploy" in result.output


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_gcp_generates_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--cloud", "gcp"])
        assert result.exit_code == 0, result.output
        assert "Dockerfile" in result.output
        assert Path("Dockerfile").exists()
        assert Path("run.py").exists()
        assert Path("terraform/main.tf").exists()
        assert Path("glean_deployment.yaml").exists()
        assert Path(".env.example").exists()


def test_init_aws_generates_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--cloud", "aws"])
        assert result.exit_code == 0, result.output
        assert Path("Dockerfile").exists()
        assert Path("terraform/main.tf").exists()


def test_init_gcp_shows_next_steps(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--cloud", "gcp"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "glean_deployment.yaml" in result.output


def test_init_aws_shows_next_steps(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--cloud", "aws"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "EKS" in result.output or "eks" in result.output.lower()


def test_init_with_custom_output_dir(runner, tmp_path):
    out = tmp_path / "output"
    result = runner.invoke(cli, ["init", "--cloud", "gcp", "--output-dir", str(out)])
    assert result.exit_code == 0
    assert (out / "Dockerfile").exists()


def test_init_with_connector_name(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--cloud", "gcp", "--connector-name", "my_jira"])
        assert result.exit_code == 0
        yaml_content = Path("glean_deployment.yaml").read_text()
        assert "my_jira" in yaml_content


# ---------------------------------------------------------------------------
# secrets upload
# ---------------------------------------------------------------------------


def test_secrets_upload_env_file_not_found(runner, tmp_path, gcp_deployment_yaml):
    result = runner.invoke(
        cli,
        ["secrets", "upload", "--env-file", str(tmp_path / "missing.env"), "--config", str(gcp_deployment_yaml)],
    )
    assert result.exit_code != 0
    assert ".env file not found" in result.output or "Error" in result.output


def test_secrets_upload_calls_upload_secrets(runner, tmp_path, gcp_deployment_yaml):
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=secret\n")

    with patch("glean.indexing.deployment.secrets.upload_secrets") as mock_upload:
        mock_upload.return_value = {"CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "created"}
        result = runner.invoke(
            cli,
            ["secrets", "upload", "--env-file", str(env_file), "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0, result.output
        mock_upload.assert_called_once()
        assert "created" in result.output


def test_secrets_upload_no_secrets(runner, tmp_path, gcp_deployment_yaml):
    env_file = tmp_path / ".env"
    env_file.write_text("")

    with patch("glean.indexing.deployment.secrets.upload_secrets") as mock_upload:
        mock_upload.return_value = {}
        result = runner.invoke(
            cli,
            ["secrets", "upload", "--env-file", str(env_file), "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0
        assert "No secrets to upload" in result.output


# ---------------------------------------------------------------------------
# destroy (confirmation prompt)
# ---------------------------------------------------------------------------


def test_destroy_prompts_for_confirmation(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # Answer "n" to abort
    with patch("subprocess.run") as mock_run:
        result = runner.invoke(
            cli,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="n\n",
        )
        assert result.exit_code != 0 or "Aborted" in result.output
        # terraform destroy should NOT have been called
        mock_run.assert_not_called()


def test_destroy_proceeds_with_yes(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            cli,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="y\n",
        )
        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# config not found
# ---------------------------------------------------------------------------


def test_apply_missing_config_shows_error(runner, tmp_path):
    result = runner.invoke(cli, ["apply", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Error" in result.output
