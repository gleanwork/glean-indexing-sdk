"""`glean-idx deploy` — generate and operate customer-hosted connector deployments.

The generation and cloud logic lives in `glean.indexing.deployment`; this module
is only the command surface.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

import click
from pydantic import ValidationError

from glean.indexing.cli.context import CliContext
from glean.indexing.cli.errors import ConfirmationRequiredError, DeploymentError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import OutputMode, emit
from glean.indexing.deployment import generate_artifacts
from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import list_generated_files
from glean.indexing.deployment.secret_manifest import (
    env_keys_from_upload_results,
    manifest_path,
    read_manifest,
    write_manifest,
)


def _confirm(ctx: click.Context, prompt: str) -> None:
    """Require confirmation for a mutating action, unless --yes was passed.

    Uniform across every destructive command: `click.confirmation_option` gives
    no escape hatch, which hangs an unattended caller with no way to proceed.
    """
    cli_ctx = context(ctx)
    if cli_ctx.assume_yes:
        return
    if cli_ctx.output is OutputMode.JSON:
        raise ConfirmationRequiredError(
            "confirmation is required for this operation",
            hint=["rerun with --yes to approve the operation non-interactively"],
            data={"operation": prompt},
        )
    click.confirm(prompt, abort=True, err=True)


def _echo_diagnostic(value: str, *, err: bool) -> None:
    """Write a captured tool stream without adding a second trailing newline."""
    if value:
        click.echo(value, err=err, nl=not value.endswith("\n"))


def _tool_error(
    message: str,
    command: list[str],
    *,
    return_code: int | None,
    stdout: str,
    stderr: str,
    hint: list[str] | None = None,
) -> DeploymentError:
    """Build a structured process failure with useful human diagnostics."""
    rendered_command = shlex.join(command)
    detail_lines = [f"Command: {rendered_command}"]
    if return_code is not None:
        detail_lines.append(f"Return code: {return_code}")
    if stdout:
        detail_lines.extend(["stdout:", stdout.rstrip()])
    if stderr:
        detail_lines.extend(["stderr:", stderr.rstrip()])

    error = DeploymentError(
        message,
        detail="\n".join(detail_lines),
        hint=hint,
        data={
            "command": command,
            "return_code": return_code,
            "stdout": stdout,
            "stderr": stderr,
        },
    )
    if return_code is not None and 1 <= return_code <= 255:
        error.exit_code = return_code
    return error


def _run_tool(
    command: list[str],
    cli_ctx: CliContext,
    *,
    failure_message: str,
    cwd: Path | None = None,
    echo_stdout: bool = True,
    stream: bool = False,
    hint: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a deploy tool and translate spawn/nonzero failures into ``DeploymentError``."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=not stream,
            text=True,
        )
    except OSError as exc:
        raise _tool_error(
            f"{failure_message} Could not start {command[0]!r}: {exc}",
            command,
            return_code=None,
            stdout="",
            stderr=str(exc),
            hint=hint,
        ) from exc

    raw_stdout = getattr(result, "stdout", None)
    raw_stderr = getattr(result, "stderr", None)
    stdout = raw_stdout if isinstance(raw_stdout, str) else ""
    stderr = raw_stderr if isinstance(raw_stderr, str) else ""
    if result.returncode != 0:
        raise _tool_error(
            failure_message,
            command,
            return_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            hint=hint,
        )

    if not stream:
        if echo_stdout:
            _echo_diagnostic(stdout, err=cli_ctx.output is OutputMode.JSON)
        _echo_diagnostic(stderr, err=True)
    return result


def _backend_error(operation: str, config: DeploymentConfig, exc: Exception) -> DeploymentError:
    """Translate an optional cloud SDK/backend failure at the CLI boundary."""
    return DeploymentError(
        f"Could not {operation} secrets in {config.cloud.upper()} Secret Manager: {exc}",
        data={
            "cloud": config.cloud,
            "operation": operation,
            "error_type": type(exc).__name__,
        },
    )


def _load_config(config_path: Path) -> DeploymentConfig:
    """Load glean_deployment.yaml or exit with a clear error."""
    if not config_path.exists():
        raise DeploymentError(
            f"Deployment config not found at {config_path}. "
            "Run `glean-idx deploy init --cloud gcp|aws` first."
        )
    try:
        return DeploymentConfig.from_yaml(config_path)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False, include_context=False, include_input=False)
        )
        raise DeploymentError(f"Invalid deployment config at {config_path}: {details}") from exc
    except Exception as exc:
        raise DeploymentError(f"Invalid deployment config at {config_path}: {exc}") from exc


@click.group()
def deploy() -> None:
    """Deploy connectors to your own cloud.

    \b
    Quickstart:
        glean-idx deploy init --cloud gcp
        # Edit glean_deployment.yaml and .env
        glean-idx deploy build --push
        glean-idx deploy secrets upload
        glean-idx deploy apply

    \b
    References:
        Kubernetes CronJobs: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
        Terraform:           https://developer.hashicorp.com/terraform/docs
        GCP GKE:             https://cloud.google.com/kubernetes-engine/docs
        AWS EKS:             https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html
        Report issues:       https://github.com/gleanwork/glean-indexing-sdk/issues
    """


@deploy.command()
@click.option("--cloud", required=True, type=click.Choice(["gcp", "aws"], case_sensitive=False))
@click.option(
    "--connector-name", default=None, help="Connector name. Defaults to current directory name."
)
@click.option("--connector-class", default="MyConnector", show_default=True)
@click.option("--connector-module", default="connector", show_default=True)
@click.option(
    "--connector-factory",
    default=None,
    help="Optional zero-argument factory in the connector module.",
)
@click.option("--output-dir", default=".", show_default=True, type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing generated deployment files.")
@global_options
@click.pass_context
def init(
    ctx: click.Context,
    cloud: str,
    connector_name: str | None,
    connector_class: str,
    connector_module: str,
    connector_factory: str | None,
    output_dir: str,
    force: bool,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Generate deployment artifacts (Dockerfile, Terraform, run.py, .env.example)."""
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    out = Path(output_dir).resolve()
    derived_name = re.sub(r"[^a-z0-9_-]+", "_", Path.cwd().name.lower()).strip("_-")
    effective_name = connector_name or derived_name or "connector"

    gcp_kwargs = (
        {
            "project_id": "<your-gcp-project-id>",
            "artifact_registry_repo": "<region>-docker.pkg.dev/<project>/connectors",
        }
        if cloud == "gcp"
        else {}
    )
    aws_kwargs = (
        {
            "account_id": "000000000000",
            "ecr_repo": "<account>.dkr.ecr.<region>.amazonaws.com/connectors",
        }
        if cloud == "aws"
        else {}
    )

    try:
        config = DeploymentConfig(
            connector_name=effective_name,
            connector_class=connector_class,
            connector_module=connector_module,
            connector_factory=connector_factory,
            cloud=cloud,  # type: ignore[arg-type]
            region="us-central1" if cloud == "gcp" else "us-east-1",
            cluster_name="<your-cluster-name>",
            **gcp_kwargs,
            **aws_kwargs,
        )
    except Exception as exc:
        raise DeploymentError(f"Could not build initial config: {exc}") from exc

    try:
        generate_artifacts(config, output_dir=out, force=force)
    except FileExistsError as exc:
        raise DeploymentError(str(exc)) from exc

    generated_files = list_generated_files(cloud)
    cloud_docs = (
        [
            "GCP GKE docs: https://cloud.google.com/kubernetes-engine/docs",
            "GCP Artifact Registry: https://cloud.google.com/artifact-registry/docs",
        ]
        if cloud == "gcp"
        else [
            "AWS EKS docs: https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html",
            "AWS ECR docs: https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html",
        ]
    )
    next_steps = [
        "Edit glean_deployment.yaml — set cluster_name, region, and registry.",
        *cloud_docs,
        "cp .env.example .env  # fill in connector credentials",
        "glean-idx deploy build --push",
        "glean-idx deploy secrets upload",
        "glean-idx deploy apply",
    ]
    data = {
        "cloud": cloud,
        "output_dir": str(out),
        "generated_files": generated_files,
        "next_steps": next_steps,
    }
    text = "\n".join(
        [
            f"Generating {cloud.upper()} deployment artifacts in {out}/",
            *[f"  created  {path}" for path in generated_files],
            "",
            "Next steps:",
            "  1. Edit glean_deployment.yaml — set cluster_name, region, and registry.",
            *[f"     {reference}" for reference in cloud_docs],
            "  2. cp .env.example .env  # fill in connector credentials",
            "  3. glean-idx deploy build --push",
            "  4. glean-idx deploy secrets upload",
            "  5. glean-idx deploy apply",
        ]
    )
    emit(data, cli_ctx.output, text=text)


@deploy.command()
@click.option("--push", is_flag=True, help="Push image to registry after building.")
@click.option("--tag", default="latest", show_default=True)
@click.option(
    "--platform",
    default="linux/amd64",
    show_default=True,
    help="Target platform for buildx (e.g. linux/amd64, linux/arm64). "
    "GKE/EKS nodes are typically linux/amd64; set this when building on Apple Silicon (arm64).",
)
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def build(
    ctx: click.Context,
    push: bool,
    tag: str,
    platform: str,
    config_path: str,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Build (and optionally push) the connector container image.

    Uses ``docker buildx`` to support cross-platform builds. When ``--push`` is
    supplied the image is pushed directly from the builder — no separate
    ``docker push`` step is needed.
    """
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    image = f"{config.image_name}:{tag}"
    build_dir = Path(config_path).resolve().parent

    # buildx build with explicit platform; --push sends directly to the registry,
    # --load pulls the result into the local docker daemon (single-platform only).
    cmd = ["docker", "buildx", "build", "--platform", platform, "-t", image]
    if push:
        cmd.append("--push")
    else:
        cmd.append("--load")
    cmd.append(".")

    _run_tool(
        cmd,
        cli_ctx,
        cwd=build_dir,
        failure_message="docker buildx build failed.",
    )

    emit(
        {"image": image, "platform": platform, "pushed": push},
        cli_ctx.output,
        text=f"Building image: {image}  (platform={platform})\nDone: {image}",
    )


@deploy.group()
def secrets() -> None:
    """Manage connector secrets in cloud secret manager."""


@secrets.command("list")
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def secrets_list(
    ctx: click.Context, config_path: str, output: str | None, assume_yes: bool
) -> None:
    """List connector secrets stored in GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import get_secrets_backend

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    try:
        keys = get_secrets_backend(config).list()
    except Exception as exc:
        raise _backend_error("list", config, exc) from exc
    data = {"connector": config.connector_name, "cloud": config.cloud, "secrets": keys}
    text = (
        f"Secrets for connector '{config.connector_name}' in {config.cloud.upper()} "
        f"({len(keys)}):\n\n" + "\n".join(f"  {key}" for key in keys)
        if keys
        else f"No secrets found for connector '{config.connector_name}' in {config.cloud.upper()}."
    )
    emit(data, cli_ctx.output, text=text)


@secrets.command("delete")
@click.argument("key")
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def secrets_delete(
    ctx: click.Context, key: str, config_path: str, output: str | None, assume_yes: bool
) -> None:
    """Delete a connector secret KEY from GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import get_secrets_backend

    context(ctx, output=output, assume_yes=assume_yes)
    _confirm(ctx, f"Permanently delete the secret {key!r}?")

    config = _load_config(Path(config_path))
    try:
        get_secrets_backend(config).delete(key)
    except KeyError:
        raise DeploymentError(
            f"Secret '{key}' not found for connector '{config.connector_name}'. "
            "Use `glean-idx deploy secrets list` to see available secrets."
        )
    except Exception as exc:
        raise _backend_error("delete", config, exc) from exc

    keys_path = manifest_path(Path(config_path))
    try:
        remaining_keys = [
            existing_key for existing_key in read_manifest(keys_path) if existing_key != key
        ]
        write_manifest(keys_path, remaining_keys)
    except (OSError, ValueError) as exc:
        raise DeploymentError(
            f"Secret was deleted, but could not update {keys_path}: {exc}"
        ) from exc
    emit(
        {"connector": config.connector_name, "deleted": key},
        context(ctx).output,
        text=f"Deleted secret '{key}' for connector '{config.connector_name}'.",
    )


@secrets.command("upload")
@click.option("--env-file", default=".env", show_default=True, type=click.Path(dir_okay=False))
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def secrets_upload(
    ctx: click.Context,
    env_file: str,
    config_path: str,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Upload connector secrets from .env to GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import get_secrets_backend

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    env_path = Path(env_file)

    if not env_path.exists():
        raise DeploymentError(
            f".env file not found: {env_path}. Copy .env.example to .env and fill in your credentials."
        )

    try:
        results = get_secrets_backend(config).upload(env_path)
    except Exception as exc:
        raise _backend_error("upload", config, exc) from exc

    keys_path = manifest_path(Path(config_path))
    try:
        env_keys = env_keys_from_upload_results(results, config.secret_prefix)
        write_manifest(keys_path, env_keys)
    except (OSError, ValueError) as exc:
        raise DeploymentError(
            f"Secrets were uploaded, but could not update {keys_path}: {exc}"
        ) from exc

    data = {
        "connector": config.connector_name,
        "cloud": config.cloud,
        "env_file": str(env_path),
        "secrets": results,
    }
    if results:
        text = "\n".join(
            [
                f"Uploading secrets from {env_path} to {config.cloud.upper()} Secret Manager...",
                *[f"  {action:8s} {name}" for name, action in results.items()],
                "",
                f"Uploaded {len(results)} secret(s).",
            ]
        )
    else:
        text = "No secrets to upload (all vars were redlisted or .env was empty)."
    emit(data, cli_ctx.output, text=text)


@deploy.command()
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@click.option(
    "--terraform-dir", default="terraform", show_default=True, type=click.Path(file_okay=False)
)
@global_options
@click.pass_context
def apply(
    ctx: click.Context,
    config_path: str,
    terraform_dir: str,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Apply generated Terraform to deploy the connector CronJob."""
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        raise DeploymentError(
            f"Terraform directory not found: {tf_dir}. Run `glean-idx deploy init` first."
        )

    keys_path = manifest_path(Path(config_path))
    try:
        secret_keys_json = json.dumps(read_manifest(keys_path))
    except (OSError, ValueError) as exc:
        raise DeploymentError(f"Could not read secret key manifest {keys_path}: {exc}") from exc

    if config.cloud == "gcp":
        var_flags = [
            f"-var=project_id={config.project_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
            f"-var=secret_keys_json={secret_keys_json}",
        ]
        if config.cluster_endpoint:
            var_flags.append(f"-var=cluster_endpoint={config.cluster_endpoint}")
    else:
        var_flags = [
            f"-var=account_id={config.account_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
            f"-var=secret_keys_json={secret_keys_json}",
        ]

    _run_tool(
        ["terraform", "init"],
        cli_ctx,
        cwd=tf_dir,
        failure_message="terraform init failed.",
    )

    # terraform runs with -auto-approve below, so this is the only thing standing
    # between an accidental invocation and mutated cloud infrastructure. Read the
    # plan first: `terraform plan` in the generated directory.
    _confirm(
        ctx,
        f"Apply Terraform to {config.cloud.upper()} "
        f"cluster {config.cluster_name!r} for connector {config.connector_name!r}?",
    )

    _run_tool(
        ["terraform", "apply", "-auto-approve"] + var_flags,
        cli_ctx,
        cwd=tf_dir,
        failure_message="terraform apply failed.",
    )

    emit(
        {
            "connector": config.connector_name,
            "cloud": config.cloud,
            "cluster": config.cluster_name,
            "applied": True,
        },
        cli_ctx.output,
        text=f"Running terraform init in {tf_dir}/\nRunning terraform apply...\nTerraform applied.",
    )


@deploy.command()
@click.option("--follow", "-f", is_flag=True)
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def logs(
    ctx: click.Context,
    follow: bool,
    config_path: str,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Show logs from the most recent connector job run."""
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))

    jobs_result = _run_tool(
        [
            "kubectl",
            "get",
            "jobs",
            "-n",
            config.namespace,
            "-l",
            f"app={config.k8s_name}",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "jsonpath={.items[-1].metadata.name}",
        ],
        cli_ctx,
        failure_message="kubectl job lookup failed.",
        echo_stdout=False,
    )
    job_name = jobs_result.stdout.strip()
    if not job_name:
        raise DeploymentError(
            f"No jobs found for connector '{config.k8s_name}' in namespace '{config.namespace}'. "
            "Has the CronJob run at least once? Use `glean-idx deploy status` to check."
        )

    cmd = ["kubectl", "logs", f"job/{job_name}", "-n", config.namespace, "--tail=200"]
    if follow:
        cmd.append("-f")

    description = f"Fetching logs for {job_name} in namespace {config.namespace}..."
    capture_logs = cli_ctx.output is OutputMode.JSON or not follow
    if not capture_logs:
        click.echo(description, err=True)
    result = _run_tool(
        cmd,
        cli_ctx,
        failure_message="kubectl logs failed.",
        echo_stdout=False,
        stream=not capture_logs,
        hint=["use `glean-idx deploy status` to see job history"],
    )

    log_output = result.stdout if isinstance(result.stdout, str) else ""
    data = {
        "connector": config.connector_name,
        "namespace": config.namespace,
        "job": job_name,
        "logs": log_output,
        "follow": follow,
    }
    if capture_logs:
        emit(data, cli_ctx.output, text=f"{description}\n{log_output}".rstrip())


@deploy.command()
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@global_options
@click.pass_context
def status(ctx: click.Context, config_path: str, output: str | None, assume_yes: bool) -> None:
    """Show CronJob status and recent job history."""
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    cronjob_result = _run_tool(
        ["kubectl", "get", "cronjob", config.k8s_name, "-n", config.namespace],
        cli_ctx,
        failure_message="kubectl status lookup failed.",
        echo_stdout=False,
    )
    jobs_result = _run_tool(
        [
            "kubectl",
            "get",
            "jobs",
            "-n",
            config.namespace,
            "-l",
            f"app={config.k8s_name}",
            "--sort-by=.metadata.creationTimestamp",
        ],
        cli_ctx,
        failure_message="kubectl status lookup failed.",
        echo_stdout=False,
    )
    cronjob_output = cronjob_result.stdout if isinstance(cronjob_result.stdout, str) else ""
    jobs_output = jobs_result.stdout if isinstance(jobs_result.stdout, str) else ""
    emit(
        {
            "connector": config.connector_name,
            "namespace": config.namespace,
            "cronjob": cronjob_output,
            "jobs": jobs_output,
        },
        cli_ctx.output,
        text=(
            f"CronJob: {config.k8s_name}  namespace: {config.namespace}\n\n"
            f"{cronjob_output}\n{jobs_output}"
        ).rstrip(),
    )


@deploy.command()
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
@click.option(
    "--terraform-dir", default="terraform", show_default=True, type=click.Path(file_okay=False)
)
@click.option(
    "--keep-secrets",
    is_flag=True,
    default=False,
    help="Keep secrets in Secret Manager (don't delete them).",
)
@global_options
@click.pass_context
def destroy(
    ctx: click.Context,
    config_path: str,
    terraform_dir: str,
    keep_secrets: bool,
    output: str | None,
    assume_yes: bool,
) -> None:
    """Tear down the connector deployment via terraform destroy.

    Destroys all Terraform-managed resources (CronJob, ServiceAccount, IAM bindings)
    and by default also deletes connector secrets from Secret Manager.

    Handles partial deployments gracefully - safe to run even if deployment was
    never completed or some resources were already deleted manually.

    Requires two confirmations: first an explicit 'yes' prompt, then typing
    the connector name to prevent accidental teardown. Pass --yes to skip
    both (intended for CI pipelines only).
    """
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    if not cli_ctx.assume_yes:
        prompt = (
            f"This will permanently destroy the '{config.connector_name}' deployment "
            "and all managed cloud resources. Continue?"
        )
        if cli_ctx.output is OutputMode.JSON:
            raise ConfirmationRequiredError(
                "confirmation is required for this operation",
                hint=["rerun with --yes to approve the operation non-interactively"],
                data={"operation": prompt},
            )
        click.confirm(prompt, abort=True, err=True)
        typed = click.prompt(
            f"Type the connector name '{config.connector_name}' to confirm", err=True
        )
        if typed != config.connector_name:
            raise DeploymentError(
                f"Confirmation failed: expected '{config.connector_name}', got '{typed}'."
            )
    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        raise DeploymentError(f"Terraform directory not found: {tf_dir}.")

    if config.cloud == "gcp":
        var_flags = [
            f"-var=project_id={config.project_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
        ]
        if config.cluster_endpoint:
            var_flags.append(f"-var=cluster_endpoint={config.cluster_endpoint}")
    else:
        var_flags = [
            f"-var=account_id={config.account_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
        ]

    _run_tool(
        ["terraform", "destroy", "-auto-approve"] + var_flags,
        cli_ctx,
        cwd=tf_dir,
        failure_message="terraform destroy failed.",
    )

    cleanup: dict[str, object] = {"kept": keep_secrets, "deleted": [], "failed": []}
    text_lines = ["Running terraform destroy...", "Terraform resources destroyed."]

    # Clean up only manifest-owned secrets unless --keep-secrets was specified.
    if not keep_secrets:
        from glean.indexing.deployment.secrets import get_secrets_backend

        text_lines.extend(["", "Cleaning up secrets from Secret Manager..."])
        keys_path = manifest_path(Path(config_path))

        try:
            secrets = read_manifest(keys_path)
        except (OSError, ValueError) as exc:
            cleanup["skipped"] = str(exc)
            click.echo(f"  Warning: secret cleanup skipped (invalid manifest): {exc}", err=True)
        else:
            if not secrets:
                text_lines.append("  No manifest-owned secrets found.")
            else:
                try:
                    backend = get_secrets_backend(config)
                except ImportError as exc:
                    cleanup["skipped"] = str(exc)
                    click.echo(
                        f"  Warning: secret cleanup skipped (missing cloud SDK dependency): {exc}",
                        err=True,
                    )
                else:
                    text_lines.append(f"  Deleting {len(secrets)} manifest-owned secret(s)...")
                    deleted: list[str] = []
                    failed: list[dict[str, str]] = []
                    for key in secrets:
                        try:
                            backend.delete(key)
                            deleted.append(key)
                            text_lines.append(f"    deleted  {key}")
                        except Exception as exc:  # noqa: BLE001 - continue cleaning up remaining secrets
                            failed.append({"key": key, "error": str(exc)})
                            click.echo(f"    failed   {key}: {exc}", err=True)
                    cleanup["deleted"] = deleted
                    cleanup["failed"] = failed
                    try:
                        write_manifest(keys_path, (failure["key"] for failure in failed))
                    except (OSError, ValueError) as exc:
                        cleanup["manifest_error"] = str(exc)
                        click.echo(f"  Warning: could not update secret manifest: {exc}", err=True)
                    text_lines.append(
                        f"  Secret cleanup complete (deleted={len(deleted)}, failed={len(failed)})."
                    )
    else:
        text_lines.extend(["", "Skipping secret cleanup (--keep-secrets specified)."])

    text_lines.extend(["", "Destroy complete."])
    emit(
        {
            "connector": config.connector_name,
            "cloud": config.cloud,
            "destroyed": True,
            "secret_cleanup": cleanup,
        },
        cli_ctx.output,
        text="\n".join(text_lines),
    )
