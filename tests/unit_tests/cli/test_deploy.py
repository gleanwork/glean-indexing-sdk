"""Unit tests for glean-deploy CLI commands."""

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
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


def test_root_output_json_wraps_deploy_init_in_one_document(runner, tmp_path):
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        cli,
        [
            "--output",
            "json",
            "deploy",
            "init",
            "--cloud",
            "gcp",
            "--connector-name",
            "my_connector",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["generated_files"]


DEPLOY_LEAVES = [
    ("apply",),
    ("build",),
    ("destroy",),
    ("init",),
    ("logs",),
    ("run",),
    ("secrets", "delete"),
    ("secrets", "list"),
    ("secrets", "upload"),
    ("status",),
]


def test_global_contract_cases_cover_every_deploy_leaf():
    def leaves(group, prefix=()):
        paths = []
        for name, command in group.commands.items():
            path = (*prefix, name)
            if hasattr(command, "commands"):
                paths.extend(leaves(command, path))
            else:
                paths.append(path)
        return paths

    assert sorted(leaves(deploy)) == DEPLOY_LEAVES


@pytest.mark.parametrize("command_path", DEPLOY_LEAVES, ids=lambda path: "-".join(path))
def test_every_deploy_leaf_accepts_global_options_in_leaf_position(runner, command_path):
    result = runner.invoke(cli, ["deploy", *command_path, "--help"])

    assert result.exit_code == 0, result.output
    assert "--output" in result.stdout
    assert "--yes" in result.stdout


@pytest.mark.parametrize("command_path", DEPLOY_LEAVES, ids=lambda path: "-".join(path))
def test_every_deploy_leaf_honors_root_json_and_yes(
    runner, tmp_path, gcp_deployment_yaml, command_path
):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir(exist_ok=True)
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=secret\n")

    args_by_path = {
        ("apply",): ["--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
        ("build",): ["--config", str(gcp_deployment_yaml)],
        ("destroy",): [
            "--config",
            str(gcp_deployment_yaml),
            "--terraform-dir",
            str(tf_dir),
            "--keep-secrets",
        ],
        ("init",): [
            "--cloud",
            "gcp",
            "--connector-name",
            "my_connector",
            "--output-dir",
            str(tmp_path / "generated"),
        ],
        ("logs",): ["--config", str(gcp_deployment_yaml)],
        ("run",): ["--config", str(gcp_deployment_yaml)],
        ("secrets", "delete"): ["API_KEY", "--config", str(gcp_deployment_yaml)],
        ("secrets", "list"): ["--config", str(gcp_deployment_yaml)],
        ("secrets", "upload"): [
            "--env-file",
            str(env_file),
            "--config",
            str(gcp_deployment_yaml),
        ],
        ("status",): ["--config", str(gcp_deployment_yaml)],
    }

    def run(command, **_kwargs):
        if "jsonpath={.items[-1].metadata.name}" in command:
            return MagicMock(returncode=0, stdout="my-salesforce-123", stderr="")
        if command[:2] == ["kubectl", "logs"]:
            return MagicMock(returncode=0, stdout="connector log\n", stderr="")
        if "cronjob" in command:
            return MagicMock(returncode=0, stdout="cronjob status\n", stderr="")
        if "jobs" in command:
            return MagicMock(returncode=0, stdout="job history\n", stderr="")
        return MagicMock(returncode=0, stdout="tool diagnostic\n", stderr="")

    backend = MagicMock()
    backend.list.return_value = ["API_KEY"]
    backend.upload.return_value = {"CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "created"}
    with (
        patch("subprocess.run", side_effect=run),
        patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=backend),
    ):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "--yes",
                "deploy",
                *command_path,
                *args_by_path[command_path],
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True
    assert "confirm" not in result.stderr.lower()


@pytest.mark.parametrize(
    "command_path",
    [("apply",), ("destroy",), ("secrets", "delete")],
    ids=lambda path: "-".join(path),
)
def test_json_confirmation_returns_an_error_without_prompting(
    runner, tmp_path, gcp_deployment_yaml, command_path
):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()
    args_by_path = {
        ("apply",): ["--config", str(gcp_deployment_yaml), "--terraform-dir", str(tf_dir)],
        ("destroy",): [
            "--config",
            str(gcp_deployment_yaml),
            "--terraform-dir",
            str(tf_dir),
            "--keep-secrets",
        ],
        ("secrets", "delete"): ["API_KEY", "--config", str(gcp_deployment_yaml)],
    }

    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                *command_path,
                *args_by_path[command_path],
            ],
        )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "confirmation_required"
    assert "[y/N]" not in result.output
    assert "Type the connector name" not in result.output


def test_json_status_keeps_tool_diagnostics_on_stderr(runner, gcp_deployment_yaml):
    results = [
        MagicMock(returncode=0, stdout="cronjob status\n", stderr="cronjob warning\n"),
        MagicMock(returncode=0, stdout="job history\n", stderr="jobs warning\n"),
    ]
    with patch("subprocess.run", side_effect=results):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                "status",
                "--config",
                str(gcp_deployment_yaml),
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["cronjob"] == "cronjob status\n"
    assert result.stderr == "cronjob warning\njobs warning\n"


def test_json_tool_failure_includes_process_diagnostics(runner, gcp_deployment_yaml):
    completed = MagicMock(
        returncode=7,
        stdout="docker build details\n",
        stderr="docker daemon error\n",
    )
    with patch("subprocess.run", return_value=completed):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                "build",
                "--config",
                str(gcp_deployment_yaml),
            ],
        )

    assert result.exit_code == 7
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "deployment_error"
    assert error["data"]["command"][:3] == ["docker", "buildx", "build"]
    assert error["data"]["return_code"] == 7
    assert error["data"]["stdout"] == "docker build details\n"
    assert error["data"]["stderr"] == "docker daemon error\n"
    assert result.stderr == ""


def test_missing_deploy_executable_is_a_structured_error(runner, gcp_deployment_yaml):
    missing = FileNotFoundError(2, "No such file or directory", "docker")
    with patch("subprocess.run", side_effect=missing):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                "build",
                "--config",
                str(gcp_deployment_yaml),
            ],
        )

    assert result.exit_code == 1
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "deployment_error"
    assert error["data"]["command"][0] == "docker"
    assert error["data"]["return_code"] is None
    assert error["data"]["stdout"] == ""
    assert "No such file or directory" in error["data"]["stderr"]


def test_cloud_backend_failure_is_a_structured_error(runner, gcp_deployment_yaml):
    backend = MagicMock()
    backend.list.side_effect = RuntimeError("cloud SDK unavailable")
    with patch("glean.indexing.deployment.secrets.get_secrets_backend", return_value=backend):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                "secrets",
                "list",
                "--config",
                str(gcp_deployment_yaml),
            ],
        )

    assert result.exit_code == 1
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "deployment_error"
    assert error["data"] == {
        "cloud": "gcp",
        "operation": "list",
        "error_type": "RuntimeError",
    }
    assert "cloud SDK unavailable" in error["message"]


def test_kubectl_nonzero_preserves_safe_return_code_and_diagnostics(runner, gcp_deployment_yaml):
    completed = MagicMock(
        returncode=23,
        stdout="partial kubectl output\n",
        stderr="cluster unavailable\n",
    )
    with patch("subprocess.run", return_value=completed):
        result = runner.invoke(
            cli,
            [
                "--output",
                "json",
                "deploy",
                "status",
                "--config",
                str(gcp_deployment_yaml),
            ],
        )

    assert result.exit_code == 23
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "deployment_error"
    assert error["data"]["command"][:3] == ["kubectl", "get", "cronjob"]
    assert error["data"]["return_code"] == 23
    assert error["data"]["stdout"] == "partial kubectl output\n"
    assert error["data"]["stderr"] == "cluster unavailable\n"


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
        result = runner.invoke(deploy, ["init", "--cloud", "gcp", "--output", "text"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "glean_deployment.yaml" in result.output
        assert result.output.index("datasource configure") < result.output.index(
            "deploy build --push"
        )
        assert result.output.index("deploy build --push") < result.output.index(
            "deploy secrets upload"
        )
        assert result.output.index("deploy apply") < result.output.index("deploy run")


def test_init_aws_shows_next_steps(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "aws", "--output", "text"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "EKS" in result.output or "eks" in result.output.lower()


def test_init_with_custom_output_dir(runner, tmp_path):
    out = tmp_path / "output"
    result = runner.invoke(
        deploy,
        [
            "init",
            "--cloud",
            "gcp",
            "--connector-name",
            "my_connector",
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert (out / "Dockerfile").exists()


def test_init_with_connector_name(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(deploy, ["init", "--cloud", "gcp", "--connector-name", "my_jira"])
        assert result.exit_code == 0
        yaml_content = Path("glean_deployment.yaml").read_text()
        assert "my_jira" in yaml_content


def test_init_sanitizes_default_name_derived_from_directory(runner, tmp_path, monkeypatch):
    project = tmp_path / "Wiki Connector---"
    project.mkdir()
    monkeypatch.chdir(project)

    result = runner.invoke(deploy, ["init", "--cloud", "gcp"])

    assert result.exit_code == 0, result.output
    assert "connector_name: wiki_connector" in (project / "glean_deployment.yaml").read_text()


def test_init_with_connector_factory(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            deploy,
            [
                "init",
                "--cloud",
                "gcp",
                "--connector-class",
                "CompanyWikiConnector",
                "--connector-factory",
                "create_connector",
            ],
        )

        assert result.exit_code == 0, result.output
        deployment = yaml.safe_load(Path("glean_deployment.yaml").read_text())
        assert deployment["connector_class"] == "CompanyWikiConnector"
        assert deployment["connector_factory"] == "create_connector"


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
                "--output",
                "text",
            ],
        )
        assert result.exit_code == 0
        assert "No secrets to upload" in result.output


def test_secrets_upload_writes_sorted_env_keys_from_backend_contract(
    runner, tmp_path, gcp_deployment_yaml
):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASS=pass\nAPI_KEY=secret\n")

    mock_backend = MagicMock()
    mock_backend.upload.return_value = {
        "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_DB_PASS": "created",
        "CUSTOM_DATASOURCE_PLATFORM_MY_SALESFORCE_API_KEY": "updated",
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
    assert (gcp_deployment_yaml.parent / ".glean_secret_keys").read_text() == "API_KEY\nDB_PASS\n"


def test_secrets_upload_rejects_malformed_backend_return_mapping(
    runner, tmp_path, gcp_deployment_yaml
):
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=secret\n")
    mock_backend = MagicMock()
    mock_backend.upload.return_value = {"API_KEY": "created"}

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

    assert result.exit_code != 0
    assert "could not update" in result.output.lower()
    assert not (gcp_deployment_yaml.parent / ".glean_secret_keys").exists()


def test_secrets_upload_atomically_rewrites_stale_manifest_when_empty(
    runner, tmp_path, gcp_deployment_yaml
):
    env_file = tmp_path / ".env"
    env_file.write_text("")
    keys_file = gcp_deployment_yaml.parent / ".glean_secret_keys"
    keys_file.write_text("STALE_KEY\n")

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

    assert result.exit_code == 0, result.output
    assert keys_file.exists()
    assert keys_file.read_bytes() == b""


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
            [
                "destroy",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
                "--output",
                "text",
            ],
            input="n\n",
        )
        assert result.exit_code != 0 or "Aborted" in result.output
        assert "Continue?" in result.stderr
        assert "Continue?" not in result.stdout
        mock_run.assert_not_called()


def test_destroy_wrong_connector_name_aborts(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    # Say "y" to the first prompt but type the wrong connector name
    with patch("subprocess.run") as mock_run:
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
                "--output",
                "text",
            ],
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
            [
                "destroy",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
                "--output",
                "text",
            ],
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


def test_destroy_reports_resources_that_remain_customer_owned(
    runner, tmp_path, gcp_deployment_yaml
):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        result = runner.invoke(
            deploy,
            [
                "destroy",
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
                "--keep-secrets",
                "--yes",
                "--output",
                "json",
            ],
        )

    assert result.exit_code == 0, result.output
    retained = json.loads(result.output)["data"]["retained"]
    assert retained == {
        "container_image": (
            "us-central1-docker.pkg.dev/my-project/connectors/my_salesforce:latest"
        ),
        "datasource_registration": "not managed by deploy",
        "kubernetes_namespace": "default",
        "local_files": ["glean_deployment.yaml", "terraform/"],
    }


def test_destroy_cleans_up_only_manifest_owned_secrets(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()
    keys_file = gcp_deployment_yaml.parent / ".glean_secret_keys"
    keys_file.write_text("API_KEY\nAPI_SECRET\n")

    mock_backend = MagicMock()
    mock_backend.list.return_value = ["API_KEY", "API_SECRET", "OTHER_CONNECTOR_KEY"]
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
                "--output",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Cleaning up secrets" in result.output
        mock_backend.list.assert_not_called()
        assert mock_backend.delete.call_count == 2
        mock_backend.delete.assert_any_call("API_KEY")
        mock_backend.delete.assert_any_call("API_SECRET")
        assert "OTHER_CONNECTOR_KEY" not in [
            args.args[0] for args in mock_backend.delete.call_args_list
        ]
        assert keys_file.read_bytes() == b""


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
                "--output",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Skipping secret cleanup" in result.output
        mock_backend.list.assert_not_called()
        mock_backend.delete.assert_not_called()


def test_destroy_no_manifest_secrets_shows_graceful_message(runner, tmp_path, gcp_deployment_yaml):
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
                "--config",
                str(gcp_deployment_yaml),
                "--terraform-dir",
                str(tf_dir),
                "--output",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "No manifest-owned secrets found" in result.output
        mock_backend.list.assert_not_called()
        mock_backend.delete.assert_not_called()


def test_destroy_handles_partial_secret_deletion_failures(runner, tmp_path, gcp_deployment_yaml):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()
    keys_file = gcp_deployment_yaml.parent / ".glean_secret_keys"
    keys_file.write_text("API_KEY\nAPI_SECRET\n")

    mock_backend = MagicMock()

    def delete_side_effect(key: str) -> None:
        if key == "API_SECRET":
            raise RuntimeError("Secret already deleted")

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
                "--output",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "deleted  API_KEY" in result.output
        assert "failed   API_SECRET" in result.stderr
        assert keys_file.read_text() == "API_SECRET\n"


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


def test_build_uses_image_tag_from_config(runner, gcp_deployment_yaml):
    config = yaml.safe_load(gcp_deployment_yaml.read_text())
    config["image_tag"] = "candidate-42"
    gcp_deployment_yaml.write_text(yaml.safe_dump(config))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(deploy, ["build", "--config", str(gcp_deployment_yaml)])

    assert result.exit_code == 0, result.output
    command = mock_run.call_args_list[0].args[0]
    assert "us-central1-docker.pkg.dev/my-project/connectors/my_salesforce:candidate-42" in command


def test_build_rejects_tag_that_would_diverge_from_apply(runner, gcp_deployment_yaml):
    with patch("subprocess.run") as mock_run:
        result = runner.invoke(
            deploy,
            [
                "build",
                "--config",
                str(gcp_deployment_yaml),
                "--tag",
                "different-tag",
            ],
        )

    assert result.exit_code != 0
    assert "image_tag" in result.output
    mock_run.assert_not_called()


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
# run
# ---------------------------------------------------------------------------


def test_run_creates_a_job_from_the_configured_cronjob(runner, gcp_deployment_yaml, monkeypatch):
    calls = []
    monkeypatch.setattr("time.time", lambda: 1_777_777_777)
    monkeypatch.setattr("uuid.uuid4", lambda: MagicMock(hex="abcdef1234567890"))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )

    result = runner.invoke(
        deploy, ["run", "--config", str(gcp_deployment_yaml), "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    assert calls[0][0] == [
        "kubectl",
        "create",
        "job",
        "--from=cronjob/my-salesforce",
        "my-salesforce-manual-1777777777-abcdef12",
        "--namespace",
        "default",
    ]
    data = json.loads(result.output)["data"]
    assert data["job"] == "my-salesforce-manual-1777777777-abcdef12"
    assert data["cronjob"] == "my-salesforce"


def test_run_generated_job_name_stays_within_kubernetes_limit(
    runner, gcp_deployment_yaml, monkeypatch
):
    config = yaml.safe_load(gcp_deployment_yaml.read_text())
    config["connector_name"] = "a" * 52
    config["service_account_name"] = "long-connector-runtime"
    gcp_deployment_yaml.write_text(yaml.safe_dump(config))
    calls = []
    monkeypatch.setattr("time.time", lambda: 1_777_777_777)
    monkeypatch.setattr("uuid.uuid4", lambda: MagicMock(hex="abcdef1234567890"))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )

    result = runner.invoke(deploy, ["run", "--config", str(gcp_deployment_yaml)])

    assert result.exit_code == 0, result.output
    job_name = calls[0][0][4]
    assert len(job_name) <= 63
    assert job_name.endswith("-manual-1777777777-abcdef12")


def test_run_names_do_not_collide_within_one_second(runner, gcp_deployment_yaml, monkeypatch):
    identifiers = iter(["aaaaaaaa11111111", "bbbbbbbb22222222"])
    monkeypatch.setattr("time.time", lambda: 1_777_777_777)
    monkeypatch.setattr("uuid.uuid4", lambda: MagicMock(hex=next(identifiers)))
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )

    first = runner.invoke(deploy, ["run", "--config", str(gcp_deployment_yaml)])
    second = runner.invoke(deploy, ["run", "--config", str(gcp_deployment_yaml)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert calls[0][0][4] != calls[1][0][4]


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_invalid_aws_account_id_reports_config_field_and_expected_format(runner, tmp_path):
    config_path = tmp_path / "custom-deployment.yaml"
    config_path.write_text(
        """
connector_name: my_connector
connector_class: MyConnector
connector_module: connector
cloud: aws
region: us-east-1
cluster_name: my-cluster
account_id: 123
ecr_repo: 123.dkr.ecr.us-east-1.amazonaws.com/connectors
"""
    )

    with patch("subprocess.run") as mock_run:
        result = runner.invoke(deploy, ["status", "--config", str(config_path)])

    assert result.exit_code != 0
    assert str(config_path) in result.output
    assert "account_id" in result.output
    assert "exactly 12 decimal digits" in result.output
    assert "errors.pydantic.dev" not in result.output
    mock_run.assert_not_called()


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
        [
            "apply",
            "--config",
            str(gcp_deployment_yaml),
            "--terraform-dir",
            str(tf_dir),
            "--output",
            "text",
        ],
        input="n\n",
    )
    assert result.exit_code != 0
    assert "Apply the Terraform plan" in result.stderr
    assert "Apply the Terraform plan" not in result.stdout
    # terraform init runs before the prompt; apply must not.
    assert not any("apply" in " ".join(map(str, call[0])) for call in calls)


def test_apply_forwards_every_mutable_config_value(runner, gcp_deployment_yaml, monkeypatch):
    config = yaml.safe_load(gcp_deployment_yaml.read_text())
    config.update(
        {
            "connector_name": "edited_connector",
            "connector_class": "EditedConnector",
            "connector_module": "edited.connector",
            "connector_factory": "create_connector",
            "region": "us-central1-a",
            "cluster_name": "edited-cluster",
            "namespace": "edited-namespace",
            "cpu": "750m",
            "memory": "768Mi",
            "cron_schedule": "*/15 * * * *",
            "indexing_mode": "INCREMENTAL",
            "project_id": "edited-project",
            "artifact_registry_repo": "us-central1-docker.pkg.dev/edited-project/connectors",
            "service_account_name": "edited-connector-runtime",
            "cluster_endpoint": "gke-abc123.us-central1-a.gke.goog",
            "image_tag": "candidate-42",
        }
    )
    gcp_deployment_yaml.write_text(yaml.safe_dump(config))
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

    assert result.exit_code == 0, result.output
    plan_command = next(call[0] for call in calls if "plan" in call[0])
    expected = {
        "connector_name": "edited_connector",
        "k8s_name": "edited-connector",
        "connector_class": "EditedConnector",
        "connector_module": "edited.connector",
        "connector_factory": "create_connector",
        "region": "us-central1-a",
        "cluster_name": "edited-cluster",
        "namespace": "edited-namespace",
        "cpu": "750m",
        "memory": "768Mi",
        "cron_schedule": "*/15 * * * *",
        "indexing_mode": "INCREMENTAL",
        "project_id": "edited-project",
        "service_account_name": "edited-connector-runtime",
        "secret_prefix": "CUSTOM_DATASOURCE_PLATFORM_EDITED_CONNECTOR_",
        "cluster_endpoint": "gke-abc123.us-central1-a.gke.goog",
        "image": "us-central1-docker.pkg.dev/edited-project/connectors/edited_connector:candidate-42",
    }
    for name, value in expected.items():
        assert f"-var={name}={value}" in plan_command


def test_apply_forwards_every_mutable_aws_config_value(runner, tmp_path, monkeypatch):
    config_path = tmp_path / "glean_deployment.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "connector_name": "edited_connector",
                "connector_class": "EditedConnector",
                "connector_module": "edited.connector",
                "connector_factory": "create_connector",
                "cloud": "aws",
                "region": "us-west-2",
                "cluster_name": "edited-cluster",
                "namespace": "edited-namespace",
                "image_tag": "candidate-42",
                "cpu": "750m",
                "memory": "768Mi",
                "cron_schedule": "*/15 * * * *",
                "indexing_mode": "INCREMENTAL",
                "account_id": "210987654321",
                "ecr_repo": ("210987654321.dkr.ecr.us-west-2.amazonaws.com/connectors"),
                "iam_role_name": "edited-connector-role",
            }
        )
    )
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: calls.append(a) or _completed(0),
    )
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()

    result = runner.invoke(
        deploy,
        [
            "apply",
            "--config",
            str(config_path),
            "--terraform-dir",
            str(tf_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    plan_command = next(call[0] for call in calls if "plan" in call[0])
    expected = {
        "connector_name": "edited_connector",
        "k8s_name": "edited-connector",
        "connector_class": "EditedConnector",
        "connector_module": "edited.connector",
        "connector_factory": "create_connector",
        "region": "us-west-2",
        "cluster_name": "edited-cluster",
        "namespace": "edited-namespace",
        "cpu": "750m",
        "memory": "768Mi",
        "cron_schedule": "*/15 * * * *",
        "indexing_mode": "INCREMENTAL",
        "account_id": "210987654321",
        "service_account_name": "edited-connector-role",
        "secret_prefix": "CUSTOM_DATASOURCE_PLATFORM_EDITED_CONNECTOR_",
        "image": (
            "210987654321.dkr.ecr.us-west-2.amazonaws.com/connectors/edited_connector:candidate-42"
        ),
    }
    for name, value in expected.items():
        assert f"-var={name}={value}" in plan_command


def test_apply_passes_sorted_manifest_keys_as_json(runner, gcp_deployment_yaml, monkeypatch):
    calls = []
    (gcp_deployment_yaml.parent / ".glean_secret_keys").write_text("DB_PASS\nAPI_KEY\n")
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

    assert result.exit_code == 0, result.output
    plan_command = next(call[0] for call in calls if "plan" in call[0])
    assert '-var=secret_keys_json=["API_KEY", "DB_PASS"]' in plan_command


def test_apply_missing_manifest_is_secretless(runner, gcp_deployment_yaml, monkeypatch):
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

    assert result.exit_code == 0, result.output
    plan_command = next(call[0] for call in calls if "plan" in call[0])
    assert "-var=secret_keys_json=[]" in plan_command


def test_apply_rejects_malformed_manifest_before_terraform(
    runner, gcp_deployment_yaml, monkeypatch
):
    (gcp_deployment_yaml.parent / ".glean_secret_keys").write_text("BAD.KEY\n")
    run = MagicMock()
    monkeypatch.setattr("subprocess.run", run)
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

    assert result.exit_code != 0
    assert "Could not read secret key manifest" in result.output
    run.assert_not_called()


def test_apply_uses_the_exact_saved_plan_it_displayed(runner, gcp_deployment_yaml, monkeypatch):
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

    assert result.exit_code == 0, result.output
    plan_command = next(call[0] for call in calls if "plan" in call[0])
    apply_command = next(call[0] for call in calls if "apply" in call[0])
    plan_path = next(
        argument.removeprefix("-out=") for argument in plan_command if argument.startswith("-out=")
    )
    assert apply_command == ["terraform", "apply", "-auto-approve", plan_path]


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
            "--output",
            "text",
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
        [
            "secrets",
            "delete",
            "MY_KEY",
            "--config",
            str(gcp_deployment_yaml),
            "--output",
            "text",
        ],
        input="n\n",
    )
    assert result.exit_code != 0
    assert "Permanently delete" in result.stderr
    assert "Permanently delete" not in result.stdout
    assert deleted == []


def test_secrets_delete_updates_manifest(runner, gcp_deployment_yaml, monkeypatch):
    deleted = []
    keys_file = gcp_deployment_yaml.parent / ".glean_secret_keys"
    keys_file.write_text("Z_KEY\nMY_KEY\nA_KEY\n")
    monkeypatch.setattr(
        "glean.indexing.deployment.secrets.get_secrets_backend",
        lambda _config: _FakeBackend(deleted),
    )

    result = runner.invoke(
        deploy,
        ["secrets", "delete", "MY_KEY", "--config", str(gcp_deployment_yaml), "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert deleted == ["MY_KEY"]
    assert keys_file.read_text() == "A_KEY\nZ_KEY\n"


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
