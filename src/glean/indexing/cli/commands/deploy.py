"""`glean-idx deploy` — generate and operate customer-hosted connector deployments.

The generation and cloud logic lives in `glean.indexing.deployment`; this module
is only the command surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from glean.indexing.cli.main import context, global_options
from glean.indexing.deployment import generate_artifacts
from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import list_generated_files


def _confirm(ctx: click.Context, prompt: str) -> None:
    """Require confirmation for a mutating action, unless --yes was passed.

    Uniform across every destructive command: `click.confirmation_option` gives
    no escape hatch, which hangs an unattended caller with no way to proceed.
    """
    if context(ctx).assume_yes:
        return
    click.confirm(prompt, abort=True)


def _load_config(config_path: Path) -> DeploymentConfig:
    """Load glean_deployment.yaml or exit with a clear error."""
    if not config_path.exists():
        raise click.ClickException(
            f"Deployment config not found at {config_path}. "
            "Run `glean-idx deploy init --cloud gcp|aws` first."
        )
    try:
        return DeploymentConfig.from_yaml(config_path)
    except Exception as exc:
        raise click.ClickException(f"Invalid glean_deployment.yaml: {exc}") from exc


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
@click.option("--output-dir", default=".", show_default=True, type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing generated deployment files.")
def init(
    cloud: str,
    connector_name: str | None,
    connector_class: str,
    connector_module: str,
    output_dir: str,
    force: bool,
) -> None:
    """Generate deployment artifacts (Dockerfile, Terraform, run.py, .env.example)."""
    out = Path(output_dir).resolve()
    effective_name = connector_name or Path.cwd().name.lower().replace("-", "_").replace(" ", "_")

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
            "account_id": "<your-aws-account-id>",
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
            cloud=cloud,  # type: ignore[arg-type]
            region="us-central1" if cloud == "gcp" else "us-east-1",
            cluster_name="<your-cluster-name>",
            **gcp_kwargs,
            **aws_kwargs,
        )
    except Exception as exc:
        raise click.ClickException(f"Could not build initial config: {exc}") from exc

    click.echo(f"Generating {cloud.upper()} deployment artifacts in {out}/")
    try:
        generate_artifacts(config, output_dir=out, force=force)
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc

    for f in list_generated_files(cloud):
        click.echo(f"  created  {f}")

    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Edit glean_deployment.yaml — set cluster_name, region, and registry.")
    if cloud == "gcp":
        click.echo(
            "     GCP GKE docs:              https://cloud.google.com/kubernetes-engine/docs"
        )
        click.echo(
            "     GCP Artifact Registry:     https://cloud.google.com/artifact-registry/docs"
        )
    else:
        click.echo(
            "     AWS EKS docs:              https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html"
        )
        click.echo(
            "     AWS ECR docs:              https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html"
        )
    click.echo("  2. cp .env.example .env  # fill in connector credentials")
    click.echo("  3. glean-idx deploy build --push")
    click.echo("  4. glean-idx deploy secrets upload")
    click.echo("  5. glean-idx deploy apply")


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
def build(push: bool, tag: str, platform: str, config_path: str) -> None:
    """Build (and optionally push) the connector container image.

    Uses ``docker buildx`` to support cross-platform builds. When ``--push`` is
    supplied the image is pushed directly from the builder — no separate
    ``docker push`` step is needed.
    """
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

    click.echo(f"Building image: {image}  (platform={platform})")
    if subprocess.run(cmd, cwd=build_dir, check=False).returncode != 0:
        raise click.ClickException("docker buildx build failed.")

    click.echo(f"Done: {image}")


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
def secrets_list(config_path: str) -> None:
    """List connector secrets stored in GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import get_secrets_backend

    config = _load_config(Path(config_path))
    keys = get_secrets_backend(config).list()

    if not keys:
        click.echo(
            f"No secrets found for connector '{config.connector_name}' in {config.cloud.upper()}."
        )
        return

    click.echo(
        f"Secrets for connector '{config.connector_name}' in {config.cloud.upper()} ({len(keys)}):\n"
    )
    for key in keys:
        click.echo(f"  {key}")


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
        raise click.ClickException(
            f"Secret '{key}' not found for connector '{config.connector_name}'. "
            "Use `glean-idx deploy secrets list` to see available secrets."
        )
    click.echo(f"Deleted secret '{key}' for connector '{config.connector_name}'.")


@secrets.command("upload")
@click.option("--env-file", default=".env", show_default=True, type=click.Path(dir_okay=False))
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
def secrets_upload(env_file: str, config_path: str) -> None:
    """Upload connector secrets from .env to GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import get_secrets_backend

    config = _load_config(Path(config_path))
    env_path = Path(env_file)

    if not env_path.exists():
        raise click.ClickException(
            f".env file not found: {env_path}. Copy .env.example to .env and fill in your credentials."
        )

    click.echo(f"Uploading secrets from {env_path} to {config.cloud.upper()} Secret Manager...")
    results = get_secrets_backend(config).upload(env_path)

    if not results:
        click.echo("No secrets to upload (all vars were redlisted or .env was empty).")
        return

    for name, action in results.items():
        click.echo(f"  {action:8s} {name}")
    click.echo(f"\nUploaded {len(results)} secret(s).")


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
    context(ctx, output=output, assume_yes=assume_yes)
    config = _load_config(Path(config_path))
    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        raise click.ClickException(
            f"Terraform directory not found: {tf_dir}. Run `glean-idx deploy init` first."
        )

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

    click.echo(f"Running terraform init in {tf_dir}/")
    if subprocess.run(["terraform", "init"], cwd=tf_dir, check=False).returncode != 0:
        raise click.ClickException("terraform init failed.")

    # terraform runs with -auto-approve below, so this is the only thing standing
    # between an accidental invocation and mutated cloud infrastructure. Read the
    # plan first: `terraform plan` in the generated directory.
    _confirm(
        ctx,
        f"Apply Terraform to {config.cloud.upper()} "
        f"cluster {config.cluster_name!r} for connector {config.connector_name!r}?",
    )

    click.echo("Running terraform apply...")
    if (
        subprocess.run(
            ["terraform", "apply", "-auto-approve"] + var_flags, cwd=tf_dir, check=False
        ).returncode
        != 0
    ):
        raise click.ClickException("terraform apply failed.")


@deploy.command()
@click.option("--follow", "-f", is_flag=True)
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
def logs(follow: bool, config_path: str) -> None:
    """Show logs from the most recent connector job run."""
    config = _load_config(Path(config_path))

    jobs_result = subprocess.run(
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
        check=False,
        capture_output=True,
        text=True,
    )
    job_name = jobs_result.stdout.strip()
    if not job_name:
        raise click.ClickException(
            f"No jobs found for connector '{config.k8s_name}' in namespace '{config.namespace}'. "
            "Has the CronJob run at least once? Use `glean-idx deploy status` to check."
        )

    cmd = ["kubectl", "logs", f"job/{job_name}", "-n", config.namespace, "--tail=200"]
    if follow:
        cmd.append("-f")

    click.echo(f"Fetching logs for {job_name} in namespace {config.namespace}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        click.echo("\nTip: Use `glean-idx deploy status` to see job history.", err=True)
        sys.exit(result.returncode)


@deploy.command()
@click.option(
    "--config",
    "config_path",
    default="glean_deployment.yaml",
    show_default=True,
    type=click.Path(dir_okay=False),
)
def status(config_path: str) -> None:
    """Show CronJob status and recent job history."""
    config = _load_config(Path(config_path))
    click.echo(f"CronJob: {config.k8s_name}  namespace: {config.namespace}\n")
    subprocess.run(
        ["kubectl", "get", "cronjob", config.k8s_name, "-n", config.namespace], check=False
    )
    click.echo()
    subprocess.run(
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
        check=False,
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
    "--yes", is_flag=True, default=False, help="Skip the confirmation prompts (use in CI only)."
)
@click.option(
    "--keep-secrets",
    is_flag=True,
    default=False,
    help="Keep secrets in Secret Manager (don't delete them).",
)
def destroy(config_path: str, terraform_dir: str, yes: bool, keep_secrets: bool) -> None:
    """Tear down the connector deployment via terraform destroy.

    Destroys all Terraform-managed resources (CronJob, ServiceAccount, IAM bindings)
    and by default also deletes connector secrets from Secret Manager.

    Handles partial deployments gracefully - safe to run even if deployment was
    never completed or some resources were already deleted manually.

    Requires two confirmations: first an explicit 'yes' prompt, then typing
    the connector name to prevent accidental teardown. Pass --yes to skip
    both (intended for CI pipelines only).
    """
    config = _load_config(Path(config_path))
    if not yes:
        click.confirm(
            f"This will permanently destroy the '{config.connector_name}' deployment and all managed cloud resources. Continue?",
            abort=True,
        )
        typed = click.prompt(f"Type the connector name '{config.connector_name}' to confirm")
        if typed != config.connector_name:
            raise click.ClickException(
                f"Confirmation failed: expected '{config.connector_name}', got '{typed}'."
            )
    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        raise click.ClickException(f"Terraform directory not found: {tf_dir}.")

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

    click.echo("Running terraform destroy...")
    if (
        subprocess.run(
            ["terraform", "destroy", "-auto-approve"] + var_flags, cwd=tf_dir, check=False
        ).returncode
        != 0
    ):
        raise click.ClickException("terraform destroy failed.")

    click.echo("Terraform resources destroyed.")

    # Clean up secrets unless --keep-secrets was specified
    if not keep_secrets:
        from glean.indexing.deployment.secrets import get_secrets_backend

        click.echo("\nCleaning up secrets from Secret Manager...")
        backend = get_secrets_backend(config)

        try:
            secrets = backend.list()
        except ImportError as exc:
            click.echo(
                f"  Warning: secret cleanup skipped (missing cloud SDK dependency): {exc}", err=True
            )
        except Exception as exc:
            click.echo(
                f"  Warning: secret cleanup skipped (failed to list secrets): {exc}", err=True
            )
        else:
            if not secrets:
                click.echo("  No secrets found (already cleaned up or never uploaded).")
            else:
                click.echo(f"  Deleting {len(secrets)} secret(s)...")
                deleted = 0
                failed = 0
                for key in secrets:
                    try:
                        backend.delete(key)
                        deleted += 1
                        click.echo(f"    deleted  {key}")
                    except Exception as exc:
                        failed += 1
                        click.echo(f"    failed   {key}: {exc}", err=True)
                click.echo(f"  Secret cleanup complete (deleted={deleted}, failed={failed}).")
    else:
        click.echo("\nSkipping secret cleanup (--keep-secrets specified).")

    click.echo("\nDestroy complete.")
