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
- Do not build, push, upload secrets, or apply until the confirmed connector plan has been revalidated against the current implementation and generated deployment configuration for production use.
- Resolve every known follow-up recorded in the connector plan or source investigation before deployment.
- Never commit `.env` or raw secrets. Use `.env.example` as the template and upload real secrets through `glean-deploy secrets upload`.
- Keep deployment-control variables separate from connector secrets. Deployment-control variables are not uploaded as connector secrets.
- The runtime is read-only toward the secret manager by default. Enable secret write-back only for refreshable short-lived tokens, scoped to the specific token secret, with a secret-scoped write IAM grant and explicit user confirmation. Never write the whole environment back and never rewrite static config or the Glean indexing token. See "Persisting refreshed tokens at runtime (secret write-back)".
- Keep `.glean` planning artifacts inside the connector folder, and deployment artifacts in the connector folder root.
- Use the connector folder as the container image build directory by default. Do not ask the user to choose an image directory.
- When pushing the image to the configured cloud container registry, use only the connector name as its repository path. Do not ask the user to choose an image path.

## Prerequisites

Before using `glean-deploy`, confirm the user has:

- The Glean Indexing SDK installed in the active Python environment. The `glean-deploy` console command is registered by the SDK package.
- Colima installed and running. If Colima is unavailable, ask the user whether they want to install and start it or use another Docker-compatible runtime, such as Docker Desktop. Verify the selected runtime is working with `docker info` before building an image.
- Cloud CLI authenticated:
  - GCP: `gcloud auth login && gcloud auth application-default login`
  - AWS: `aws configure`
- **GCP only**: verify no stale service account impersonation is active before deploying:
  ```bash
  gcloud config get auth/impersonate_service_account
  # If set, clear it: gcloud config unset auth/impersonate_service_account
  ```
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

# 2. Build and push container image (linux/amd64 by default — correct for GKE/EKS amd64 nodes)
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

## Known Issues and Mitigations

### arm64 build on Apple Silicon → amd64 GKE/EKS nodes

`glean-deploy build` uses `docker buildx` and defaults to `--platform linux/amd64`. This is correct for all standard GKE and EKS node pools (amd64). Do not override unless the cluster is explicitly running arm64 nodes.

If you see `exec format error` in pod logs, confirm the image platform:
```bash
docker inspect <image> | grep Architecture
# Should be: "amd64"
```

### Private GKE cluster — Terraform kubernetes provider timeout

Symptom: GCP-side resources (service account, IAM roles, Workload Identity) apply successfully, but Terraform fails creating Kubernetes resources with a connection timeout to a private IP (e.g. `10.x.x.x`).

Cause: `data.google_container_cluster.main.endpoint` returns the private IP for clusters with `enablePublicEndpoint: false`. The generated Terraform uses `coalesce(var.cluster_endpoint, endpoint)` to allow override.

Fix: get the GKE DNS endpoint and add it to `glean_deployment.yaml`:
```bash
gcloud container clusters describe <cluster-name> \
  --region <region> \
  --format="value(privateClusterConfig.privateEndpoint,controlPlaneEndpointsConfig.dnsEndpointConfig.endpoint)"
```
Then set in `glean_deployment.yaml`:
```yaml
cluster_endpoint: "abc123def.gke.goog"   # the *.gke.goog DNS hostname
```

`glean-deploy apply` and `glean-deploy destroy` both pick this up automatically.

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
| `glean-deploy destroy` | Tear down the deployment — two-step confirmation: y/n prompt then type the connector name. |
| `glean-deploy destroy --yes` | Tear down without prompts (CI only). |

For `glean-deploy init`, only `--cloud` is required. If omitted, `--connector-name` defaults to the current directory name, `--connector-class` defaults to `MyConnector`, and `--connector-module` defaults to `connector`. Pass those options when the generated connector uses different names.

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
- optional `cluster_endpoint` — required for private-only GKE clusters (see Known Issues)

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

### Persisting refreshed tokens at runtime (secret write-back)

By default the runtime is read-only: `run.py` loads secrets from the secret manager
into the process environment at the start of every run and never writes anything back.
The pod's service account is granted only read roles
(`roles/secretmanager.secretAccessor` + `roles/secretmanager.viewer` on GCP).

Enable write-back **only** for connectors that authenticate with a **refreshable,
short-lived credential** (OAuth access/refresh tokens, session tokens) that the source
issues anew during a run and that must survive to the next run. This is the correct use
of the secret manager. Do **not** enable write-back to "save the environment" generally.

Rules for write-back:

- **Scope the write to the specific token secret(s) only.** Never write the whole
  environment back. Static config (categories, base URLs, User-Agent) and the Glean
  indexing token must not be rewritten — doing so churns a new secret version every run
  and can clobber a value rotated out-of-band.
- **For OAuth, persist BOTH the access token and the refresh token.** Many providers use
  refresh-token rotation — each refresh returns a new refresh token and invalidates the
  old one. Write back both the refreshed access token and the new refresh token (as their
  own scoped secrets). If only the access token is persisted, the next run authenticates
  with a stale refresh token and fails.
- **Grant the minimum IAM, scoped to the one secret**, and only after explicit user
  confirmation (this changes the connector's runtime security posture):

  ```bash
  # GCP: allow adding new versions of ONE secret, not project-wide
  gcloud secrets add-iam-policy-binding \
    CUSTOM_DATASOURCE_PLATFORM_<CONNECTOR_NAME>_<TOKEN_KEY> \
    --project <project_id> \
    --member "serviceAccount:<connector_name>-sa@<project_id>.iam.gserviceaccount.com" \
    --role roles/secretmanager.secretVersionAdder
  ```

  On AWS, grant `secretsmanager:PutSecretValue` on the single secret ARN via the
  connector's IRSA role.
- **Write a new version only when the value actually changed**, right after the refresh,
  so a failed run never persists a partial or empty token.

Minimal helper the connector calls after refreshing a token (GCP):

```python
from google.cloud import secretmanager

def persist_secret(project_id: str, secret_id: str, value: str) -> None:
    """Add a new version of a single secret (e.g. a refreshed OAuth token)."""
    client = secretmanager.SecretManagerServiceClient()
    client.add_secret_version(
        parent=f"projects/{project_id}/secrets/{secret_id}",
        payload={"data": value.encode("utf-8")},
    )

# After an OAuth refresh, persist BOTH tokens (refresh-token rotation invalidates the old
# refresh token). Only write a token whose value actually changed.
if new_access_token != old_access_token:
    persist_secret(project_id, "CUSTOM_DATASOURCE_PLATFORM_<NAME>_ACCESS_TOKEN", new_access_token)
if new_refresh_token != old_refresh_token:
    persist_secret(project_id, "CUSTOM_DATASOURCE_PLATFORM_<NAME>_REFRESH_TOKEN", new_refresh_token)
```

Record in `connector_plan.md` which secret keys are written back and why, and confirm the
scoped IAM grant with the user before applying it.

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

## Pre-deployment Revalidation

After generating and configuring the deployment artifacts, immediately before running any build, push, secret-upload, or apply command:

1. Re-read the confirmed `<connector-folder>/.glean/connector_plan.md` and `<connector-folder>/.glean/source_investigation.md`.
2. Compare every local-testing assumption with its production requirement, including source authentication, scopes and permissions, secret names, endpoints, and runtime configuration.
3. Inspect the current connector implementation and deployment configuration to verify that every production requirement in the plan is implemented and configured. A successful local test does not prove that a different production path is ready.
4. If anything required for production is missing, incomplete, still marked as a validation gap, or recorded as a known follow-up, stop before building or running any cloud-mutating command. Explain the specific gaps and follow-ups, ask the user for the required decisions or setup, make the necessary implementation or configuration changes, update the plan, and ask the user to reconfirm it.
5. Never deploy a test-only mechanism when the plan specifies a different production mechanism. Do not build or deploy until the planned production mechanism is implemented and configured.

## Recommended Sequence

After connector code and plan are ready:

1. `glean-deploy init --cloud gcp|aws` (optionally add `--connector-name <name> --connector-class <ClassName> --connector-module <module>` when defaults do not match)
2. Edit `glean_deployment.yaml`.
3. Copy `.env.example` to `.env` and fill secrets locally.
4. Complete the pre-deployment revalidation above and resolve every production-readiness gap and known follow-up.
5. `glean-deploy build --push`
6. `glean-deploy secrets upload`
7. `glean-deploy apply`
8. `glean-deploy status`
9. `glean-deploy logs`
10. Inspect the deployed connector logs and confirm the connector actually ran: lifecycle start/completion or failure, source fetch counts, transform counts, upload attempts/results, and no leaked secrets.

Use `glean-deploy destroy` only when the user explicitly wants teardown.

`destroy` requires two confirmations interactively: a y/n prompt then typing the connector name. This prevents accidental teardown of production deployments. For CI pipelines use `--yes` to skip both.

```bash
glean-deploy destroy
# Prompt 1: "This will permanently destroy 'my_connector'... Continue? [y/N]"
# Prompt 2: "Type the connector name 'my_connector' to confirm:"
```

## Evaluation

For planning-only evals, do not run cloud commands. The deployment plan should be enough.

For implementation evals with cloud access, verify:

- `glean-deploy init` creates all expected artifacts.
- `glean_deployment.yaml` validates for the selected cloud.
- The connector plan and source investigation contain no unresolved known follow-ups.
- The implemented and configured production auth path matches the confirmed plan rather than a test-only auth path.
- `.env` excludes deployment-control variables from uploaded connector secrets.
- `secrets upload` is run only after user confirmation.
- `apply`, `status`, `logs`, and `destroy` are run only in an approved test environment.
- After deployment, actual deployed connector logs show the expected lifecycle/fetch/transform/upload events and no secret values.
