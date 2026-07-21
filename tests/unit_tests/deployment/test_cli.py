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

    mock_backend = MagicMock()
    mock_backend.upload.return_value = {"CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "created"}
    with patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend):
        result = runner.invoke(
            cli,
            ["secrets", "upload", "--env-file", str(env_file), "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0, result.output
        mock_backend.upload.assert_called_once()
        assert "created" in result.output


def test_secrets_upload_no_secrets(runner, tmp_path, gcp_deployment_yaml):
    env_file = tmp_path / ".env"
    env_file.write_text("")

    mock_backend = MagicMock()
    mock_backend.upload.return_value = {}
    with patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend):
        result = runner.invoke(
            cli,
            ["secrets", "upload", "--env-file", str(env_file), "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0
        assert "No secrets to upload" in result.output


# ---------------------------------------------------------------------------
# destroy (2-step confirmation)
# ---------------------------------------------------------------------------


def test_destroy_first_prompt_abort(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # Answer "n" to the first prompt — terraform must not run
    with patch("subprocess.run") as mock_run:
        result = runner.invoke(
            cli,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="n\n",
        )
        assert result.exit_code != 0 or "Aborted" in result.output
        mock_run.assert_not_called()


def test_destroy_wrong_connector_name_aborts(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # Say "y" to the first prompt but type the wrong connector name
    with patch("subprocess.run") as mock_run:
        result = runner.invoke(
            cli,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="y\nwrong_name\n",
        )
        assert result.exit_code != 0
        assert "Confirmation failed" in result.output or "Error" in result.output
        mock_run.assert_not_called()


def test_destroy_two_step_confirmation_succeeds(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # First: "y", second: connector name from fixture ("my_salesforce")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            cli,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="y\nmy_salesforce\n",
        )
        assert result.exit_code == 0, result.output
        assert mock_run.called


def test_destroy_yes_flag_skips_prompts(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # --yes should skip both confirmation prompts entirely
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            cli,
            ["destroy", "--yes", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.called


# ---------------------------------------------------------------------------
# config not found
# ---------------------------------------------------------------------------


def test_apply_missing_config_shows_error(runner, tmp_path):
    result = runner.invoke(cli, ["apply", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_build_invokes_docker_build(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            cli,
            ["build", "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0, result.output
        build_call = mock_run.call_args_list[0]
        cmd = build_call.args[0]
        assert "docker" in cmd
        assert "buildx" in cmd
        assert "build" in cmd
        assert "--platform" in cmd
        assert "linux/amd64" in cmd
        assert "--load" in cmd  # no --push → load into local daemon


def test_build_uses_config_parent_as_cwd(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        runner.invoke(cli, ["build", "--config", str(gcp_deployment_yaml)])
        build_call = mock_run.call_args_list[0]
        assert build_call.kwargs.get("cwd") == gcp_deployment_yaml.parent


def test_build_push_calls_docker_push(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            cli,
            ["build", "--push", "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0, result.output
        # buildx build --push is a single command (no separate docker push step)
        assert mock_run.call_count == 1
        cmd = mock_run.call_args_list[0].args[0]
        assert "--push" in cmd
        assert "--load" not in cmd


def test_build_missing_config_shows_error(runner, tmp_path):
    result = runner.invoke(cli, ["build", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


def test_logs_fetches_latest_job_then_logs(runner, tmp_path, gcp_deployment_yaml):
    def _side_effect(cmd, **kwargs):
        if "get" in cmd and "jobs" in cmd:
            mock = MagicMock(returncode=0, stdout="my-salesforce-28123456")
            return mock
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_side_effect):
        result = runner.invoke(cli, ["logs", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code == 0, result.output
        assert "my-salesforce-28123456" in result.output


def test_logs_no_jobs_shows_error(runner, tmp_path, gcp_deployment_yaml):
    def _side_effect(cmd, **kwargs):
        if "get" in cmd and "jobs" in cmd:
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_side_effect):
        result = runner.invoke(cli, ["logs", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code != 0
        assert "No jobs found" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_shows_cronjob_and_jobs(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(cli, ["status", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 2
        # First call: kubectl get cronjob
        assert "cronjob" in mock_run.call_args_list[0].args[0]
        # Second call: kubectl get jobs with label selector
        jobs_cmd = mock_run.call_args_list[1].args[0]
        assert "jobs" in jobs_cmd
        assert any("app=" in arg for arg in jobs_cmd)
