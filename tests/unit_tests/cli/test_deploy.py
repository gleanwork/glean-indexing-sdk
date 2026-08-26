"""Unit tests for glean-deploy CLI commands."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from glean.indexing.cli.commands.deploy import deploy
from glean.indexing.cli.main import cli


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
    result = runner.invoke(deploy, ["--help"])
    assert result.exit_code == 0
    assert "glean-idx deploy" in result.output


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_gcp_generates_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "gcp"])
        assert result.exit_code == 0, result.output
        assert "Dockerfile" in result.output
        assert Path("Dockerfile").exists()
        assert Path("run.py").exists()
        assert Path("terraform/main.tf").exists()
        assert Path("glean_deployment.yaml").exists()
        assert Path(".env.example").exists()


def test_init_public_cli_exposes_force(runner):
    result = runner.invoke(cli, ["deploy", "init", "--help"])

    assert result.exit_code == 0, result.output
    assert "--force" in result.output
    assert "Overwrite existing generated deployment files" in result.output


def test_init_fresh_project_adds_gitignore_protections(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])

        assert result.exit_code == 0, result.output
        assert Path(".gitignore").read_text().splitlines() == [
            ".env",
            ".terraform/",
            "*.tfstate*",
        ]


def test_init_collision_aborts_before_writes_and_preserves_existing_bytes(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        original = b"user-owned Dockerfile\n\xff\x00"
        Path("Dockerfile").write_bytes(original)

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])

        assert result.exit_code != 0
        assert "Dockerfile" in result.output
        assert "--force" in result.output
        assert Path("Dockerfile").read_bytes() == original
        assert not Path("run.py").exists()
        assert not Path(".gitignore").exists()


def test_init_lists_all_collisions_without_partial_generation(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        existing = {
            "Dockerfile": b"custom Dockerfile\n",
            "run.py": b"custom runner\n",
            ".env.example": b"CUSTOM_SECRET=\n",
        }
        for path, content in existing.items():
            Path(path).write_bytes(content)

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])

        assert result.exit_code != 0
        for path, content in existing.items():
            assert path in result.output
            assert Path(path).read_bytes() == content
        assert not Path("glean_deployment.yaml").exists()
        assert not Path("terraform").exists()
        assert not Path(".gitignore").exists()


def test_init_parent_path_collision_is_atomic_even_with_force(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform").write_bytes(b"user-owned path\n")

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp", "--force"])

        assert result.exit_code != 0
        assert "terraform" in result.output
        assert Path("terraform").read_bytes() == b"user-owned path\n"
        assert not Path("Dockerfile").exists()
        assert not Path(".gitignore").exists()


def test_init_lists_gitignore_and_generated_conflicts_before_writing(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path(".gitignore").mkdir()
        Path("Dockerfile").write_bytes(b"user-owned Dockerfile\n")

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])

        assert result.exit_code != 0
        assert ".gitignore" in result.output
        assert "Dockerfile" in result.output
        assert Path("Dockerfile").read_bytes() == b"user-owned Dockerfile\n"
        assert not Path("run.py").exists()
        assert not Path("terraform").exists()


def test_init_force_overwrites_generated_file_collisions(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("Dockerfile").write_text("user-owned Dockerfile\n")

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp", "--force"])

        assert result.exit_code == 0, result.output
        assert Path("Dockerfile").read_text() != "user-owned Dockerfile\n"
        assert Path("run.py").exists()
        assert Path("terraform/main.tf").exists()


def test_init_merges_gitignore_protections_without_replacing_user_content(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        original = b"# User rules\r\nbuild/\r\n"
        Path(".gitignore").write_bytes(original)

        result = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])

        assert result.exit_code == 0, result.output
        merged = Path(".gitignore").read_bytes()
        assert merged == original + b".env\r\n.terraform/\r\n*.tfstate*\r\n"


def test_init_gitignore_merge_is_idempotent(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path(".gitignore").write_bytes(b"build/")

        first = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp"])
        assert first.exit_code == 0, first.output
        merged = Path(".gitignore").read_bytes()

        second = runner.invoke(cli, ["deploy", "init", "--cloud", "gcp", "--force"])

        assert second.exit_code == 0, second.output
        assert Path(".gitignore").read_bytes() == merged
        assert merged == b"build/\n.env\n.terraform/\n*.tfstate*\n"


def test_init_aws_generates_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "aws"])
        assert result.exit_code == 0, result.output
        assert Path("Dockerfile").exists()
        assert Path("terraform/main.tf").exists()


def test_init_gcp_shows_next_steps(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "gcp"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "glean_deployment.yaml" in result.output


def test_init_aws_shows_next_steps(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "aws"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "EKS" in result.output or "eks" in result.output.lower()


def test_init_with_custom_output_dir(runner, tmp_path):
    out = tmp_path / "output"
    result = runner.invoke(deploy, ["init", "--cloud", "gcp", "--output-dir", str(out)])
    assert result.exit_code == 0
    assert (out / "Dockerfile").exists()


def test_init_with_connector_name(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "gcp", "--connector-name", "my_jira"])
        assert result.exit_code == 0
        yaml_content = Path("glean_deployment.yaml").read_text()
        assert "my_jira" in yaml_content


# ---------------------------------------------------------------------------
# secrets upload
# ---------------------------------------------------------------------------


def test_secrets_upload_env_file_not_found(runner, tmp_path, gcp_deployment_yaml):
    result = runner.invoke(
        deploy,
        [
            "secrets",
            "upload",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--config",
            str(gcp_deployment_yaml),
        ],
    )
    assert result.exit_code != 0
    assert ".env file not found" in result.output or "Error" in result.output


def test_secrets_upload_calls_upload_secrets(runner, tmp_path, gcp_deployment_yaml):
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=secret\n")

    mock_backend = MagicMock()
    mock_backend.upload.return_value = {
        "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "created"
    }
    with patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend):
        result = runner.invoke(
            deploy,
            [
                "secrets",
                "upload",
                "--env-file",
                str(env_file),
                "--config",
                str(gcp_deployment_yaml),
            ],
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
            deploy,
            [
                "secrets",
                "upload",
                "--env-file",
                str(env_file),
                "--config",
                str(gcp_deployment_yaml),
            ],
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
            deploy,
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
            deploy,
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
    mock_backend = MagicMock()
    mock_backend.list.return_value = []
    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            ["destroy", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
            input="y\nmy_salesforce\n",
        )
        assert result.exit_code == 0, result.output
        assert mock_run.called


def test_destroy_yes_flag_skips_prompts(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # --yes should skip both confirmation prompts entirely
    mock_backend = MagicMock()
    mock_backend.list.return_value = []
    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--yes",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.called


def test_destroy_cleans_up_secrets_by_default(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    mock_backend = MagicMock()
    mock_backend.list.return_value = ["API_KEY", "API_SECRET"]
    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--yes",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Cleaning up secrets" in result.output
        assert mock_backend.list.called
        assert mock_backend.delete.call_count == 2
        mock_backend.delete.assert_any_call("API_KEY")
        mock_backend.delete.assert_any_call("API_SECRET")


def test_destroy_keep_secrets_flag_skips_cleanup(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    mock_backend = MagicMock()
    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--yes",
                "--keep-secrets",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Skipping secret cleanup" in result.output
        mock_backend.list.assert_not_called()
        mock_backend.delete.assert_not_called()


def test_destroy_no_secrets_shows_graceful_message(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    mock_backend = MagicMock()
    mock_backend.list.return_value = []
    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--yes",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "No secrets found" in result.output
        assert "already cleaned up or never uploaded" in result.output


def test_destroy_handles_partial_secret_deletion_failures(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    mock_backend = MagicMock()
    mock_backend.list.return_value = ["API_KEY", "API_SECRET"]

    def delete_side_effect(key: str) -> None:
        if key == "API_SECRET":
            raise Exception("Secret already deleted")

    mock_backend.delete.side_effect = delete_side_effect

    with (
        patch("subprocess.run") as mock_run,
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=mock_backend),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--yes",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "deleted  API_KEY" in result.output
        assert "failed   API_SECRET" in result.stderr


# ---------------------------------------------------------------------------
# config not found
# ---------------------------------------------------------------------------


def test_apply_missing_config_shows_error(runner, tmp_path):
    result = runner.invoke(deploy, ["apply", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_build_invokes_docker_build(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
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
        runner.invoke(deploy, ["build", "--config", str(gcp_deployment_yaml)])
        build_call = mock_run.call_args_list[0]
        assert build_call.kwargs.get("cwd") == gcp_deployment_yaml.parent


def test_build_push_calls_docker_push(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            deploy,
            ["build", "--push", "--config", str(gcp_deployment_yaml)],
        )
        assert result.exit_code == 0, result.output
        # buildx build --push is a single command (no separate docker push step)
        assert mock_run.call_count == 1
        cmd = mock_run.call_args_list[0].args[0]
        assert "--push" in cmd
        assert "--load" not in cmd


def test_build_missing_config_shows_error(runner, tmp_path):
    result = runner.invoke(deploy, ["build", "--config", str(tmp_path / "missing.yaml")])
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
        result = runner.invoke(deploy, ["logs", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code == 0, result.output
        assert "my-salesforce-28123456" in result.output


def test_logs_no_jobs_shows_error(runner, tmp_path, gcp_deployment_yaml):
    def _side_effect(cmd, **kwargs):
        if "get" in cmd and "jobs" in cmd:
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_side_effect):
        result = runner.invoke(deploy, ["logs", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code != 0
        assert "No jobs found" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_shows_cronjob_and_jobs(runner, tmp_path, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(deploy, ["status", "--config", str(gcp_deployment_yaml)])
        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 2
        # First call: kubectl get cronjob
        assert "cronjob" in mock_run.call_args_list[0].args[0]
        # Second call: kubectl get jobs with label selector
        jobs_cmd = mock_run.call_args_list[1].args[0]
        assert "jobs" in jobs_cmd
        assert any("app=" in arg for arg in jobs_cmd)


# --- destructive-command confirmation -------------------------------------
#
# `apply` runs terraform with -auto-approve, and previously had no prompt at all
# while `destroy` asked twice — the inverse of the risk. `secrets delete` used
# click.confirmation_option, which offers no escape hatch and so hangs an
# unattended caller. Both now share one prompt-plus---yes contract.


def test_apply_prompts_before_mutating_infrastructure(runner, gcp_deployment_yaml, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )
    tf_dir = gcp_deployment_yaml.parent / "terraform"
    tf_dir.mkdir(exist_ok=True)
    result = runner.invoke(
        deploy,
        ["apply", "--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
        input="n\n",
    )
    assert result.exit_code != 0
    # terraform init runs before the prompt; apply must not.
    assert not any("apply" in " ".join(map(str, call[0])) for call in calls)


def test_apply_yes_flag_skips_the_prompt(runner, gcp_deployment_yaml, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )
    tf_dir = gcp_deployment_yaml.parent / "terraform"
    tf_dir.mkdir(exist_ok=True)
    result = runner.invoke(
        deploy,
        [
            "apply",
            "--config",
            str(gcp_deployment_yaml),
            "--terraform-dir",
            str(tf_dir),
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert any("apply" in " ".join(map(str, call[0])) for call in calls)


def test_secrets_delete_prompts_by_default(runner, gcp_deployment_yaml, monkeypatch):
    deleted = []
    monkeypatch.setattr(
        "glean.indexing.deployment.secrets.get_secrets_backend",
        lambda _config: _FakeBackend(deleted),
    )
    result = runner.invoke(
        deploy,
        ["secrets", "delete", "MY_KEY", "--config", str(gcp_deployment_yaml)],
        input="n\n",
    )
    assert result.exit_code != 0
    assert deleted == []


def test_secrets_delete_yes_flag_makes_it_unattended(runner, gcp_deployment_yaml, monkeypatch):
    deleted = []
    monkeypatch.setattr(
        "glean.indexing.deployment.secrets.get_secrets_backend",
        lambda _config: _FakeBackend(deleted),
    )
    result = runner.invoke(
        deploy,
        ["secrets", "delete", "MY_KEY", "--config", str(gcp_deployment_yaml), "--yes"],
    )
    assert result.exit_code == 0
    assert deleted == ["MY_KEY"]


class _FakeBackend:
    """Matches the real backend surface in deployment/secrets.py."""

    def __init__(self, deleted):
        self._deleted = deleted

    def delete(self, key):
        self._deleted.append(key)

    def list(self):
        return ["MY_KEY"]


@dataclass
class _Completed:
    """Stands in for subprocess.CompletedProcess, which the CLI only reads
    `returncode` off."""

    returncode: int


def _completed(returncode: int) -> _Completed:
    return _Completed(returncode=returncode)
