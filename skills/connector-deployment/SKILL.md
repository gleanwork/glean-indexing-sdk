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

## Supported Deployment Surface

Use the `glean-deploy` CLI:

- `glean-deploy init --cloud gcp|aws`: generates deployment artifacts.
- `glean-deploy build [--push]`: builds the connector Docker image and optionally pushes it.
- `glean-deploy secrets upload`: uploads connector secrets from `.env`.
- `glean-deploy secrets list`: lists connector secret keys already stored in cloud secret manager.
- `glean-deploy secrets delete <KEY>`: deletes one connector secret after confirmation.
- `glean-deploy apply`: runs Terraform to deploy the Kubernetes CronJob.
- `glean-deploy status`: shows CronJob and recent job status.
- `glean-deploy logs [--follow]`: shows logs from the most recent connector job.
- `glean-deploy destroy`: tears down the deployment after confirmation.

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

## Evaluation

For planning-only evals, do not run cloud commands. The deployment plan should be enough.

For implementation evals with cloud access, verify:

- `glean-deploy init` creates all expected artifacts.
- `glean_deployment.yaml` validates for the selected cloud.
- `.env` excludes deployment-control variables from uploaded connector secrets.
- `secrets upload` is run only after user confirmation.
- `apply`, `status`, `logs`, and `destroy` are run only in an approved test environment.
