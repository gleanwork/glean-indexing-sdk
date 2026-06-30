"""glean-deploy CLI entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from glean.indexing.deployment.config import DeploymentConfig
from glean.indexing.deployment.generator import generate_artifacts, list_generated_files


def _load_config(config_path: Path) -> DeploymentConfig:
    """Load glean_deployment.yaml or exit with a clear error."""
    if not config_path.exists():
        raise click.ClickException(
            f"Deployment config not found at {config_path}. "
            "Run `glean-deploy init --cloud gcp|aws` first."
        )
    try:
        return DeploymentConfig.from_yaml(config_path)
    except Exception as exc:
        raise click.ClickException(f"Invalid glean_deployment.yaml: {exc}") from exc


@click.group()
@click.version_option(package_name="glean-indexing-sdk")
def cli() -> None:
    """glean-deploy: deploy Glean custom connectors to your own cloud.

    \b
    Quickstart:
        glean-deploy init --cloud gcp
        # Edit glean_deployment.yaml and .env
        glean-deploy build --push
        glean-deploy secrets upload
        glean-deploy apply

    \b
    References:
        Kubernetes CronJobs: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
        Terraform:           https://developer.hashicorp.com/terraform/docs
        GCP GKE:             https://cloud.google.com/kubernetes-engine/docs
        AWS EKS:             https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html
    """


@cli.command()
@click.option("--cloud", required=True, type=click.Choice(["gcp", "aws"], case_sensitive=False))
@click.option("--connector-name", default=None, help="Connector name. Defaults to current directory name.")
@click.option("--connector-class", default="MyConnector", show_default=True)
@click.option("--connector-module", default="connector", show_default=True)
@click.option("--output-dir", default=".", show_default=True, type=click.Path(file_okay=False))
def init(cloud: str, connector_name: str | None, connector_class: str, connector_module: str, output_dir: str) -> None:
    """Generate deployment artifacts (Dockerfile, Terraform, run.py, .env.example)."""
    out = Path(output_dir).resolve()
    effective_name = connector_name or Path.cwd().name.lower().replace("-", "_").replace(" ", "_")

    gcp_kwargs = (
        {"project_id": "<your-gcp-project-id>", "artifact_registry_repo": "<region>-docker.pkg.dev/<project>/connectors"}
        if cloud == "gcp"
        else {}
    )
    aws_kwargs = (
        {"account_id": "<your-aws-account-id>", "ecr_repo": "<account>.dkr.ecr.<region>.amazonaws.com/connectors"}
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
    generate_artifacts(config, output_dir=out)

    for f in list_generated_files(cloud):
        click.echo(f"  created  {f}")

    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Edit glean_deployment.yaml — set cluster_name, region, and registry.")
    if cloud == "gcp":
        click.echo("     GCP GKE docs:              https://cloud.google.com/kubernetes-engine/docs")
        click.echo("     GCP Artifact Registry:     https://cloud.google.com/artifact-registry/docs")
    else:
        click.echo("     AWS EKS docs:              https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html")
        click.echo("     AWS ECR docs:              https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html")
    click.echo("  2. cp .env.example .env  # fill in connector credentials")
    click.echo("  3. glean-deploy build --push")
    click.echo("  4. glean-deploy secrets upload")
    click.echo("  5. glean-deploy apply")


@cli.command()
@click.option("--push", is_flag=True, help="Push image to registry after building.")
@click.option("--tag", default="latest", show_default=True)
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
def build(push: bool, tag: str, config_path: str) -> None:
    """Build (and optionally push) the connector container image."""
    config = _load_config(Path(config_path))
    image = f"{config.image_name}:{tag}"
    build_dir = Path(config_path).resolve().parent

    click.echo(f"Building image: {image}")
    if subprocess.run(["docker", "build", "-t", image, "."], cwd=build_dir, check=False).returncode != 0:
        raise click.ClickException("docker build failed.")

    if push:
        click.echo(f"Pushing image: {image}")
        if subprocess.run(["docker", "push", image], check=False).returncode != 0:
            raise click.ClickException("docker push failed.")

    click.echo(f"Done: {image}")


@cli.group()
def secrets() -> None:
    """Manage connector secrets in cloud secret manager."""


@secrets.command("upload")
@click.option("--env-file", default=".env", show_default=True, type=click.Path(dir_okay=False))
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
def secrets_upload(env_file: str, config_path: str) -> None:
    """Upload connector secrets from .env to GCP Secret Manager or AWS Secrets Manager."""
    from glean.indexing.deployment.secrets import upload_secrets

    config = _load_config(Path(config_path))
    env_path = Path(env_file)

    if not env_path.exists():
        raise click.ClickException(
            f".env file not found: {env_path}. Copy .env.example to .env and fill in your credentials."
        )

    click.echo(f"Uploading secrets from {env_path} to {config.cloud.upper()} Secret Manager...")
    results = upload_secrets(config, env_path)

    if not results:
        click.echo("No secrets to upload (all vars were redlisted or .env was empty).")
        return

    for name, action in results.items():
        click.echo(f"  {action:8s} {name}")
    click.echo(f"\nUploaded {len(results)} secret(s).")


@cli.command()
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
@click.option("--terraform-dir", default="terraform", show_default=True, type=click.Path(file_okay=False))
def apply(config_path: str, terraform_dir: str) -> None:
    """Apply generated Terraform to deploy the connector CronJob."""
    config = _load_config(Path(config_path))
    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        raise click.ClickException(f"Terraform directory not found: {tf_dir}. Run `glean-deploy init` first.")

    if config.cloud == "gcp":
        var_flags = [
            f"-var=project_id={config.project_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
        ]
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

    click.echo("Running terraform apply...")
    if subprocess.run(["terraform", "apply", "-auto-approve"] + var_flags, cwd=tf_dir, check=False).returncode != 0:
        raise click.ClickException("terraform apply failed.")


@cli.command()
@click.option("--follow", "-f", is_flag=True)
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
def logs(follow: bool, config_path: str) -> None:
    """Show logs from the most recent connector job run."""
    config = _load_config(Path(config_path))

    jobs_result = subprocess.run(
        [
            "kubectl", "get", "jobs",
            "-n", config.namespace,
            "-l", f"app={config.k8s_name}",
            "--sort-by=.metadata.creationTimestamp",
            "-o", "jsonpath={.items[-1].metadata.name}",
        ],
        check=False, capture_output=True, text=True,
    )
    job_name = jobs_result.stdout.strip()
    if not job_name:
        raise click.ClickException(
            f"No jobs found for connector '{config.k8s_name}' in namespace '{config.namespace}'. "
            "Has the CronJob run at least once? Use `glean-deploy status` to check."
        )

    cmd = ["kubectl", "logs", f"job/{job_name}", "-n", config.namespace, "--tail=200"]
    if follow:
        cmd.append("-f")

    click.echo(f"Fetching logs for {job_name} in namespace {config.namespace}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        click.echo("\nTip: Use `glean-deploy status` to see job history.", err=True)
        sys.exit(result.returncode)


@cli.command()
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
def status(config_path: str) -> None:
    """Show CronJob status and recent job history."""
    config = _load_config(Path(config_path))
    click.echo(f"CronJob: {config.k8s_name}  namespace: {config.namespace}\n")
    subprocess.run(["kubectl", "get", "cronjob", config.k8s_name, "-n", config.namespace], check=False)
    click.echo()
    subprocess.run(
        ["kubectl", "get", "jobs", "-n", config.namespace, "-l", f"app={config.k8s_name}", "--sort-by=.metadata.creationTimestamp"],
        check=False,
    )


@cli.command()
@click.option("--config", "config_path", default="glean_deployment.yaml", show_default=True, type=click.Path(dir_okay=False))
@click.option("--terraform-dir", default="terraform", show_default=True, type=click.Path(file_okay=False))
@click.confirmation_option(prompt="This will destroy the connector deployment. Are you sure?")
def destroy(config_path: str, terraform_dir: str) -> None:
    """Tear down the connector deployment via terraform destroy."""
    config = _load_config(Path(config_path))
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
    else:
        var_flags = [
            f"-var=account_id={config.account_id}",
            f"-var=region={config.region}",
            f"-var=cluster_name={config.cluster_name}",
            f"-var=namespace={config.namespace}",
            f"-var=image={config.image_name}:latest",
        ]

    click.echo("Running terraform destroy...")
    if subprocess.run(["terraform", "destroy", "-auto-approve"] + var_flags, cwd=tf_dir, check=False).returncode != 0:
        raise click.ClickException("terraform destroy failed.")
    click.echo("Deployment destroyed.")
