# Webex connector — finishing the deploy from inside the VPC

The `glean-deploy` GKE cluster has a **private-only control plane** (API endpoint
`192.168.16.2`), so `terraform apply` cannot reach it from a laptop. Everything
else is already provisioned; only the Kubernetes objects remain.

## Already done (from the workstation)

- ✅ Artifact Registry repo `glean-connectors` (us-central1)
- ✅ Image pushed: `us-central1-docker.pkg.dev/dev-sandbox-334901/glean-connectors/webex:latest` (linux/amd64)
- ✅ 6 secrets in GCP Secret Manager under `CUSTOM_DATASOURCE_PLATFORM_WEBEX_`
- ✅ GCP service account `webex-sa@dev-sandbox-334901.iam.gserviceaccount.com` + IAM
  (secretmanager.viewer/accessor, logging.logWriter, monitoring.metricWriter) + Workload Identity binding
  (`default/webex-ksa` ⇄ `webex-sa`)

## Remaining (must run from a VPC-connected host)

Only two resources are left in the Terraform plan:
`kubernetes_service_account_v1.connector` and `kubernetes_cron_job_v1.connector`.

### Prerequisites on the VPC host
- Terraform ≥ 1.0
- `gcloud auth application-default login` (or a SA) with access to `dev-sandbox-334901`
- Network path to the cluster's private endpoint. On a GCE VM in the cluster's VPC:
  `gcloud container clusters get-credentials glean-deploy --zone us-central1-a --project dev-sandbox-334901 --internal-ip`

### Steps
1. Copy the `examples/webex/terraform/` directory to the VPC host **including `terraform.tfstate`**
   (the state already records the GCP resources, so they won't be recreated — only the
   two K8s objects will be added).

2. Apply:
   ```bash
   cd terraform
   terraform init
   terraform apply -auto-approve \
     -var=project_id=dev-sandbox-334901 \
     -var=region=us-central1-a \
     -var=cluster_name=glean-deploy \
     -var=namespace=default \
     -var=image=us-central1-docker.pkg.dev/dev-sandbox-334901/glean-connectors/webex:latest
   ```
   (Equivalently, from a full SDK checkout on that host:
   `glean-deploy apply --config ../glean_deployment.yaml --terraform-dir .`)

## Verify

```bash
kubectl get cronjob webex -n default
# Trigger a one-off run now (don't wait for the 6-hourly schedule):
kubectl create job --from=cronjob/webex webex-manual-001 -n default
kubectl logs -f job/webex-manual-001 -n default
```

Expect logs: "Loaded 6 secret(s)…", Webex auth OK, event counts, then
`bulkindexdocuments` 200 against `https://glean-dev-be.glean.com`.

## Notes

- Schedule: `17 */6 * * *` (every 6 hours), `concurrencyPolicy: Forbid`.
- The pod reads secrets from Secret Manager at runtime via Workload Identity — no
  secrets are baked into the image.
- To change config later, edit `glean_deployment.yaml`, re-run
  `glean-deploy apply` (image/vars) or regenerate artifacts for schedule changes.
