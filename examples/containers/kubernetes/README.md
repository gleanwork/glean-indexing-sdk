# Kubernetes Example

Deploy a Glean connector as a Kubernetes CronJob for scheduled execution.

## Overview

This example provides:

- **CronJob manifests** - Scheduled connector execution
- **ConfigMap/Secret** - Configuration management
- **Kustomize** - Easy customization for different environments

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               Namespace: glean-connectors            │   │
│  │                                                       │   │
│  │  ┌─────────────┐  ┌─────────────┐                   │   │
│  │  │  ConfigMap  │  │   Secret    │                   │   │
│  │  │  (config)   │  │  (tokens)   │                   │   │
│  │  └──────┬──────┘  └──────┬──────┘                   │   │
│  │         │                │                           │   │
│  │         └────────┬───────┘                           │   │
│  │                  │                                   │   │
│  │                  ▼                                   │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │           CronJob (2 AM UTC)                 │   │   │
│  │  │  ┌─────────────────────────────────────┐   │   │   │
│  │  │  │              Job                     │   │   │   │
│  │  │  │  ┌─────────────────────────────┐   │   │   │   │
│  │  │  │  │           Pod               │   │   │   │   │
│  │  │  │  │  ┌─────────────────────┐   │───┼───┼───┼──► Glean API
│  │  │  │  │  │    Connector        │   │   │   │   │   │
│  │  │  │  │  └─────────────────────┘   │   │   │   │   │
│  │  │  │  └─────────────────────────────┘   │   │   │   │
│  │  │  └─────────────────────────────────────┘   │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Kubernetes cluster (1.21+)
- kubectl configured
- Container registry access

## Project Structure

```
kubernetes/
  k8s/
    namespace.yaml     # Dedicated namespace
    configmap.yaml     # Non-sensitive configuration
    secret.yaml        # API tokens (template)
    cronjob.yaml       # Scheduled jobs
    kustomization.yaml # Kustomize configuration
  Dockerfile           # Container image
  README.md
```

## Quick Start

### 1. Build and Push Image

```bash
# Build the image
docker build -t your-registry/glean-connector:v1.0.0 .

# Push to registry
docker push your-registry/glean-connector:v1.0.0
```

### 2. Create Secrets

```bash
# Create secrets (don't commit actual values!)
kubectl create secret generic connector-secrets \
  --namespace glean-connectors \
  --from-literal=GLEAN_INSTANCE=your-instance \
  --from-literal=GLEAN_INDEXING_API_TOKEN=your-token \
  --from-literal=SOURCE_API_KEY=your-source-key \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 3. Update Kustomization

Edit `k8s/kustomization.yaml`:

```yaml
images:
  - name: your-registry/glean-connector
    newName: your-actual-registry/glean-connector
    newTag: v1.0.0
```

### 4. Deploy

```bash
# Preview what will be created
kubectl kustomize k8s/

# Apply to cluster
kubectl apply -k k8s/
```

## CronJob Configuration

### Schedules

The example includes two CronJobs:

| CronJob | Schedule | Mode | Description |
|---------|----------|------|-------------|
| `full-sync` | `0 2 * * *` | FULL | Daily at 2 AM UTC |
| `incremental-sync` | `0 9-18 * * 1-5` | INCREMENTAL | Hourly during business hours |

### Modify Schedules

Edit `k8s/cronjob.yaml`:

```yaml
spec:
  schedule: "0 4 * * *"  # Changed to 4 AM UTC
```

### Timezone Support

For Kubernetes 1.27+, add timezone:

```yaml
spec:
  schedule: "0 2 * * *"
  timeZone: "America/Los_Angeles"
```

## Managing Jobs

### View CronJobs

```bash
kubectl get cronjobs -n glean-connectors
```

### View Job History

```bash
kubectl get jobs -n glean-connectors
```

### View Logs

```bash
# Most recent job
kubectl logs -n glean-connectors job/glean-connector-full-sync-xxxxx

# Follow logs
kubectl logs -n glean-connectors -f job/glean-connector-full-sync-xxxxx
```

### Trigger Manual Run

```bash
kubectl create job --from=cronjob/glean-connector-full-sync \
  -n glean-connectors \
  manual-sync-$(date +%s)
```

### Suspend/Resume

```bash
# Suspend
kubectl patch cronjob glean-connector-full-sync \
  -n glean-connectors \
  -p '{"spec":{"suspend":true}}'

# Resume
kubectl patch cronjob glean-connector-full-sync \
  -n glean-connectors \
  -p '{"spec":{"suspend":false}}'
```

## Customization

### Multiple Connectors

Create separate CronJobs for each connector:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: wiki-connector
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: connector
              image: your-registry/wiki-connector:latest
              args: ["--mode", "FULL"]
```

### Environment-Specific Overlays

Create Kustomize overlays for different environments:

```
k8s/
  base/
    kustomization.yaml
    ...
  overlays/
    dev/
      kustomization.yaml
    staging/
      kustomization.yaml
    production/
      kustomization.yaml
```

### Resource Limits

Adjust based on your data volume:

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

## Monitoring

### Prometheus Metrics

Add pod annotations for Prometheus scraping:

```yaml
template:
  metadata:
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/port: "8080"
```

### Alerts

Example PrometheusRule for failed jobs:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: connector-alerts
spec:
  groups:
    - name: connector
      rules:
        - alert: ConnectorJobFailed
          expr: kube_job_failed{namespace="glean-connectors"} > 0
          for: 5m
          labels:
            severity: warning
```

## Cleanup

```bash
# Delete all resources
kubectl delete -k k8s/

# Or delete namespace (removes everything)
kubectl delete namespace glean-connectors
```

## Production Considerations

1. **Image Registry** - Use a private registry with image scanning
2. **RBAC** - Create a dedicated ServiceAccount with minimal permissions
3. **Network Policies** - Restrict egress to only Glean API
4. **Pod Security** - Use Pod Security Standards
5. **Secrets** - Use external secret management (Vault, AWS Secrets Manager)
6. **Monitoring** - Set up alerts for job failures
7. **Logging** - Configure log aggregation (Loki, CloudWatch, etc.)

## Next Steps

- Add Prometheus/Grafana monitoring
- Set up GitOps with ArgoCD or Flux
- Implement external secret management
- Add network policies for security
