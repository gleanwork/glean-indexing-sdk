---
name: connector-deployment
description: Plan and operate customer-hosted deployment for Glean Indexing SDK connectors using glean-deploy. Use when the user wants deployment artifacts, cloud secrets, Kubernetes CronJobs, logs, status, or teardown for a generated connector.
---

# Connector Deployment

Use this skill when deployment or hosting is in scope for a connector build. It covers the SDK's `glean-deploy` CLI for customer self-deployment to GCP or AWS.

## Inputs

- `<connector-folder>/.glean/connector_plan.md`
- Generated connector code and Python module/class names
- Target cloud: `gcp` or `aws`
- Cloud project/account, region, Kubernetes cluster, namespace, and container registry
- Expected crawl schedule and resource sizing from the confirmed connector plan

## Rules

- Use `glean-deploy` for deployment artifacts and operations. Do not invent Terraform, Docker, Kubernetes, or secret-manager files by hand.
- Do not run cloud-mutating commands (`secrets upload`, `apply`, `destroy`) without explicit user confirmation.
- Never commit `.env` or raw secrets. Use `.env.example` as the template and upload real secrets through `glean-deploy secrets upload`.
- Keep deployment-control variables separate from connector secrets. Deployment-control variables are not uploaded as connector secrets.
- Keep `.glean` planning artifacts inside the connector folder, and deployment artifacts in the connector folder root.

## Prerequisites

Before using `glean-deploy`, confirm the user has:

- The Glean Indexing SDK installed in the active Python environment. The `glean-deploy` console command is registered by the SDK package.
- Docker running locally.
- Cloud CLI authenticated:
  - GCP: `gcloud auth login`
  - AWS: `aws configure`
- `glean_deployment.yaml` in the connector project directory.
- `.env` in the connector project directory, created from `.env.example`.
- For deployment operations, access to the target Kubernetes cluster and container registry.

## Running The CLI

If the SDK is installed, use `glean-deploy` directly:

```bash
glean-deploy --help
```

From a local SDK checkout, the user can run the same CLI without separately installing the package:

```bash
uv run glean-deploy --help
```

Use the same `uv run` prefix for any command when working from the SDK checkout, for example `uv run glean-deploy init --cloud gcp`.

## Happy Path

Use this sequence for a normal customer-hosted deployment:

```bash
# 1. Scaffold deployment files
glean-deploy init --cloud gcp   # or --cloud aws
# Edit glean_deployment.yaml: image registry, schedule, cluster, resources, etc.
# Edit .env: GLEAN_INDEXING_API_TOKEN, GLEAN_SERVER_URL, source credentials, etc.

# 2. Build and push container image
glean-deploy build --push

# 3. Upload secrets from .env to cloud secret manager
glean-deploy secrets upload

# 4. Deploy the Kubernetes CronJob
glean-deploy apply
```

After deployment:

```bash
glean-deploy status
glean-deploy logs -f
```

## Command Reference

Use the `glean-deploy` CLI:

| Command | What it does |
| --- | --- |
| `glean-deploy init --cloud gcp|aws` | Scaffold `Dockerfile`, `terraform/`, `run.py`, `glean_deployment.yaml`, and `.env.example`. |
| `glean-deploy build` | Build the connector container image locally. |
| `glean-deploy build --push` | Build and push the connector image to the configured registry. |
| `glean-deploy build --tag v1.2` | Build with a specific image tag instead of `latest`. |
| `glean-deploy secrets upload` | Upload connector secrets from `.env` to GCP Secret Manager or AWS Secrets Manager. |
| `glean-deploy secrets list` | List connector secrets currently stored in the cloud. |
| `glean-deploy secrets delete KEY` | Delete a specific connector secret after confirmation. |
| `glean-deploy apply` | Run Terraform apply to deploy or update the Kubernetes CronJob. |
| `glean-deploy status` | Show CronJob status and recent job history. |
| `glean-deploy logs` | Show logs from the most recent run. |
| `glean-deploy logs -f` | Tail logs in follow mode. |
| `glean-deploy destroy` | Tear down the deployment with confirmation. |
| `glean-deploy destroy --yes` | Tear down the deployment without an interactive confirmation prompt. |

Use the Python deployment APIs only when writing tests or advanced tooling:

- `DeploymentConfig`
- `generate_artifacts`

## Generated Artifacts

`glean-deploy init` generates:

- `Dockerfile`
- `run.py`
- `terraform/main.tf`
- `terraform/variables.tf`
- `glean_deployment.yaml`
- `.env.example`

For GCP, generated artifacts target GKE, Artifact Registry, Secret Manager, and Workload Identity.

For AWS, generated artifacts target EKS, ECR, Secrets Manager, and IRSA.

## Deployment Config

Ensure `glean_deployment.yaml` has the correct fields before running build/apply:

- `connector_name`
- `connector_class`
- `connector_module`
- `cloud`
- `region`
- `cluster_name`
- `namespace`
- `cpu`
- `memory`
- `cron_schedule`
- `indexing_mode`

For GCP, also confirm:

- `project_id`
- `artifact_registry_repo`
- optional `service_account_name`

For AWS, also confirm:

- `account_id`
- `ecr_repo`
- optional `iam_role_name`

## Secret Handling

Use `.env.example` to create `.env`, then run `glean-deploy secrets upload`.

The secret name prefix is:

```text
CUSTOM_DATASOURCE_PLATFORM_<CONNECTOR_NAME>_
```

The deployment code redlists deployment-control variables so they are not uploaded as connector secrets:

- `GOOGLE_CLOUD_PROJECT`
- `AWS_REGION`
- `DATASOURCE_NAME`
- `CLOUD_PLATFORM`
- `INDEXING_MODE`
- `CONNECTOR_CLASS`
- `CONNECTOR_MODULE`

Connector secrets should include values such as:

- `GLEAN_SERVER_URL`
- `GLEAN_INDEXING_API_TOKEN`
- source API tokens, API keys, OAuth client secrets, or other connector-specific credentials

To rotate a secret:

```bash
glean-deploy secrets delete OLD_KEY
glean-deploy secrets upload
```

To inspect currently uploaded connector secrets:

```bash
glean-deploy secrets list
```

## Plan Fields

Before implementation or deployment, ensure `<connector-folder>/.glean/connector_plan.md` records:

- Whether deployment is in scope or out of scope.
- Target cloud: GCP, AWS, or undecided.
- Connector module and class name.
- Container registry target.
- Kubernetes cluster, namespace, and region.
- Cron schedule and why it matches the full-crawl frequency decision.
- CPU and memory request/limit choice.
- Secret keys needed at runtime, without secret values.
- Whether the user confirmed running cloud-mutating commands.

## Recommended Sequence

After connector code and plan are ready:

1. `glean-deploy init --cloud gcp|aws --connector-name <name> --connector-class <ClassName> --connector-module <module>`
2. Edit `glean_deployment.yaml`.
3. Copy `.env.example` to `.env` and fill secrets locally.
4. `glean-deploy build --push`
5. `glean-deploy secrets upload`
6. `glean-deploy apply`
7. `glean-deploy status`
8. `glean-deploy logs`

Use `glean-deploy destroy` only when the user explicitly wants teardown.

For complete teardown:

```bash
glean-deploy destroy --yes
```

## Evaluation

For planning-only evals, do not run cloud commands. The deployment plan should be enough.

For implementation evals with cloud access, verify:

- `glean-deploy init` creates all expected artifacts.
- `glean_deployment.yaml` validates for the selected cloud.
- `.env` excludes deployment-control variables from uploaded connector secrets.
- `secrets upload` is run only after user confirmation.
- `apply`, `status`, `logs`, and `destroy` are run only in an approved test environment.
