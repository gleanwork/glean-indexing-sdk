---
name: connector-deployment
description: Plan and operate customer-hosted deployment for Glean Indexing SDK connectors using glean-idx deploy. Use when the user wants deployment artifacts, cloud secrets, Kubernetes CronJobs, logs, status, or teardown for a generated connector.
---

# Connector Deployment

Use this skill when deployment or hosting is in scope for a connector build. It covers the SDK's `glean-idx deploy` CLI for customer self-deployment to GCP or AWS.

## Inputs

- `<connector-folder>/.glean/connector_plan.md`
- Generated connector code and Python module/class names
- A zero-argument connector factory name when the connector class takes dependencies
- Target cloud: `gcp` or `aws`
- Cloud project/account, region, Kubernetes cluster, namespace, and container registry
- Expected crawl schedule and resource sizing from the confirmed connector plan

## Rules

- Use `glean-idx deploy` for connector-specific deployment artifacts and operations. It delegates to Docker Buildx, Terraform, provider SDKs, and `kubectl`; keep those standard tools and their authentication visible rather than inventing files or alternate clients by hand.
- Treat the cloud project/account, cluster, registry, Workload Identity/IRSA foundation, and namespace as customer-managed prerequisites. Do not create or delete them implicitly.
- Do not run cloud-mutating commands (`secrets upload`, `apply`, `destroy`) without explicit user confirmation.
- Do not build, push, upload secrets, or apply until the confirmed connector plan has been revalidated against the current implementation and generated deployment configuration for production use.
- Resolve every known follow-up recorded in the connector plan or source investigation before deployment.
- Never commit `.env` or raw secrets. Use `.env.example` as the template and upload real secrets through `glean-idx deploy secrets upload`.
- Keep deployment-control variables separate from connector secrets. Deployment-control variables are not uploaded as connector secrets.
- Prefer a module-level zero-argument `create_connector()` factory for production wiring. Cloud runners load secrets into environment variables before calling it; never put source credentials in `glean_deployment.yaml` or factory metadata.
- Keep `.glean` planning artifacts inside the connector folder, and deployment artifacts in the connector folder root.
- Use the connector folder as the container image build directory by default. Do not ask the user to choose an image directory.
- When pushing the image to the configured cloud container registry, use only the connector name as its repository path. Do not ask the user to choose an image path.

## Prerequisites

Before using `glean-idx deploy`, confirm the user has:

- The Glean Indexing SDK installed in the active Python environment. The `glean-idx deploy` console command is registered by the SDK package.
- A Docker-compatible runtime, such as Docker Desktop or Colima, with Buildx. Verify it with `docker info` and `docker buildx version`.
- Terraform 1.0 or later and `kubectl`.
- Cloud CLI authenticated:
  - GCP: `gcloud auth login --update-adc`, Artifact Registry Docker authentication, and explicit cluster credentials.
  - AWS: an authenticated AWS profile, ECR Docker authentication, and explicit EKS kubeconfig.
- An existing cluster, container registry repository, workload identity foundation, and Kubernetes namespace.
- **GCP only**: verify no stale service account impersonation is active before deploying:
  ```bash
  gcloud config get auth/impersonate_service_account
  # If set, clear it: gcloud config unset auth/impersonate_service_account
  ```
- `glean_deployment.yaml` in the connector project directory.
- `.env` in the connector project directory, created from `.env.example`.
- For deployment operations, access to the target Kubernetes cluster and container registry.

## Running The CLI

Deployment commands are subcommands of `glean-idx`, the SDK's single CLI:

```bash
glean-idx deploy --help
```

These commands read `glean_deployment.yaml` from the connector project, so run
them from inside that project. From a local SDK checkout, prefix with `uv run`:

```bash
uv run glean-idx deploy --help
```

`glean-idx doctor` checks credentials before any of this, and needs no project:

```bash
uvx --from glean-indexing-sdk glean-idx doctor
```

## Happy Path

Use this sequence for a normal customer-hosted deployment:

```bash
# 1. Scaffold deployment files
glean-idx deploy init --cloud gcp --connector-factory create_connector   # or --cloud aws
# Edit glean_deployment.yaml: image registry, schedule, cluster, resources, etc.
# Edit .env: GLEAN_INDEXING_API_TOKEN, GLEAN_SERVER_URL, source credentials, etc.

# 2. Register the API-facing datasource configuration.
glean-idx datasource configure

# 3. Build and push the configured image/tag (linux/amd64 by default).
glean-idx deploy build --push

# 4. Upload exact secrets from .env to cloud secret manager.
glean-idx deploy secrets upload

# 5. Display an exact Terraform plan, confirm it, and apply that same plan.
glean-idx deploy apply

# 6. Start one Job immediately instead of waiting for the schedule.
glean-idx deploy run
```

After deployment:

```bash
glean-idx deploy status
glean-idx deploy logs -f
glean-idx document status --datasource NAME --document TYPE ID --poll
```

## Known Issues and Mitigations

### arm64 build on Apple Silicon → amd64 GKE/EKS nodes

`glean-idx deploy build` uses `docker buildx` and defaults to `--platform linux/amd64`. This is correct for all standard GKE and EKS node pools (amd64). Do not override unless the cluster is explicitly running arm64 nodes.

If you see `exec format error` in pod logs, confirm the image platform:
```bash
docker inspect <image> | grep Architecture
# Should be: "amd64"
```

### Private GKE control-plane endpoint

For private-only clusters, the machine running Terraform needs network access to either the private IP or a GKE DNS control-plane endpoint. The generated provider uses the cluster CA for the discovered IP endpoint and system trust for an explicit DNS endpoint.

Get the GKE DNS endpoint and add it to `glean_deployment.yaml`:
```bash
gcloud container clusters describe <cluster-name> \
  --region <region> \
  --format="value(privateClusterConfig.privateEndpoint,controlPlaneEndpointsConfig.dnsEndpointConfig.endpoint)"
```
Then set in `glean_deployment.yaml`:
```yaml
cluster_endpoint: "abc123def.gke.goog"   # the *.gke.goog DNS hostname
```

`glean-idx deploy apply` and `glean-idx deploy destroy` both pick this up automatically.

## Command Reference

Use the `glean-idx deploy` CLI:

| Command | What it does |
| --- | --- |
| `glean-idx deploy init --cloud gcp|aws` | Scaffold `Dockerfile`, `terraform/`, `run.py`, `glean_deployment.yaml`, and `.env.example`. |
| `glean-idx deploy build` | Build the connector container image locally. |
| `glean-idx deploy build --push` | Build and push the connector image to the configured registry. |
| `glean-idx deploy build --tag v1.2` | Compatibility check only: the value must match `image_tag` in the YAML so build and apply cannot diverge. |
| `glean-idx deploy secrets upload` | Upload connector secrets from `.env` to GCP Secret Manager or AWS Secrets Manager. |
| `glean-idx deploy secrets list` | List connector secrets currently stored in the cloud. |
| `glean-idx deploy secrets delete KEY` | Delete a specific connector secret after confirmation. |
| `glean-idx deploy apply` | Run Terraform init, display an exact saved plan, prompt, and apply that same plan. |
| `glean-idx deploy run` | Create one immediate Job from the configured CronJob and namespace. |
| `glean-idx deploy status` | Show CronJob status and recent job history. |
| `glean-idx deploy logs` | Show logs from the most recent run. |
| `glean-idx deploy logs -f` | Tail logs in follow mode. |
| `glean-idx deploy destroy` | Tear down Terraform resources and manifest-owned secrets, then report retained image, namespace, datasource registration, and local files. Two-step confirmation: y/n prompt then type the connector name. |
| `glean-idx deploy destroy --yes` | Tear down without prompts (CI only). |

For `glean-idx deploy init`, only `--cloud` is required. If omitted, `--connector-name` defaults to the current directory name, `--connector-class` defaults to `MyConnector`, and `--connector-module` defaults to `connector`. Pass those options when the generated connector uses different names. When the class takes a name, data client, or other dependencies, pass `--connector-factory create_connector`; the named module-level function must take no arguments and return an instance of `connector_class`.

Use the Python deployment APIs only when writing tests or advanced tooling:

- `DeploymentConfig`
- `generate_artifacts`

## Generated Artifacts

`glean-idx deploy init` generates:

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
- `connector_factory` (optional zero-argument production construction hook)
- `cloud` (fixed by provider-specific artifacts at `deploy init`; rerun init to change providers)
- `region`
- `cluster_name`
- `namespace` (must already exist and remains customer-managed)
- `image_tag`
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

Use `.env.example` to create `.env`, then run `glean-idx deploy secrets upload`.

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
- `CONNECTOR_FACTORY`

Connector secrets should include values such as:

- `GLEAN_SERVER_URL`
- `GLEAN_INDEXING_API_TOKEN`
- source API tokens, API keys, OAuth client secrets, or other connector-specific credentials

To rotate a secret:

```bash
glean-idx deploy secrets delete OLD_KEY
glean-idx deploy secrets upload
```

To inspect currently uploaded connector secrets:

```bash
glean-idx deploy secrets list
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

## Pre-deployment Revalidation

After generating and configuring the deployment artifacts, immediately before running any build, push, secret-upload, or apply command:

1. Re-read the confirmed `<connector-folder>/.glean/connector_plan.md` and `<connector-folder>/.glean/source_investigation.md`.
2. Compare every local-testing assumption with its production requirement, including source authentication, scopes and permissions, secret names, endpoints, and runtime configuration.
3. Inspect the current connector implementation and deployment configuration to verify that every production requirement in the plan is implemented and configured. A successful local test does not prove that a different production path is ready.
4. If anything required for production is missing, incomplete, still marked as a validation gap, or recorded as a known follow-up, stop before building or running any cloud-mutating command. Explain the specific gaps and follow-ups, ask the user for the required decisions or setup, make the necessary implementation or configuration changes, update the plan, and ask the user to reconfirm it.
5. Never deploy a test-only mechanism when the plan specifies a different production mechanism. Do not build or deploy until the planned production mechanism is implemented and configured.

## Recommended Sequence

After connector code and plan are ready:

1. `glean-idx deploy init --cloud gcp|aws` (optionally add `--connector-name <name> --connector-class <ClassName> --connector-module <module>` when defaults do not match)
2. Edit `glean_deployment.yaml`.
3. Copy `.env.example` to `.env` and fill secrets locally.
4. Complete the pre-deployment revalidation above and resolve every production-readiness gap and known follow-up.
5. `glean-idx deploy build --push`
6. `glean-idx deploy secrets upload`
7. `glean-idx deploy apply`
8. `glean-idx deploy status`
9. `glean-idx deploy logs`
10. Inspect the deployed connector logs and confirm the connector actually ran: lifecycle start/completion or failure, source fetch counts, transform counts, upload attempts/results, and no leaked secrets.

Use `glean-idx deploy destroy` only when the user explicitly wants teardown.

`destroy` requires two confirmations interactively: a y/n prompt then typing the connector name. This prevents accidental teardown of production deployments. For CI pipelines use `--yes` to skip both.

```bash
glean-idx deploy destroy
# Prompt 1: "This will permanently destroy 'my_connector'... Continue? [y/N]"
# Prompt 2: "Type the connector name 'my_connector' to confirm:"
```

## Evaluation

For planning-only evals, do not run cloud commands. The deployment plan should be enough.

For implementation evals with cloud access, verify:

- `glean-idx deploy init` creates all expected artifacts.
- `glean_deployment.yaml` validates for the selected cloud.
- The connector plan and source investigation contain no unresolved known follow-ups.
- The implemented and configured production auth path matches the confirmed plan rather than a test-only auth path.
- `.env` excludes deployment-control variables from uploaded connector secrets.
- `secrets upload` is run only after user confirmation.
- `apply`, `status`, `logs`, and `destroy` are run only in an approved test environment.
- After deployment, actual deployed connector logs show the expected lifecycle/fetch/transform/upload events and no secret values.
