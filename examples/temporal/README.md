# Temporal Workflow Examples

[Temporal](https://temporal.io/) provides durable execution for your connectors with automatic retries, scheduling, and observability. This is the **recommended approach for production deployments**.

## Why Temporal?

| Feature | Benefit for Connectors |
|---------|------------------------|
| **Durable Execution** | Workflows survive process restarts and failures |
| **Automatic Retries** | Failed API calls are retried with configurable backoff |
| **Scheduling** | Built-in cron-like scheduling for regular syncs |
| **Observability** | Web UI shows workflow history, logs, and metrics |
| **Versioning** | Safe deployment of connector updates |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Temporal Cluster                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Scheduler  │  │   History   │  │    Matching         │ │
│  │  (Cron)     │  │   Service   │  │    Service          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Worker Process                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  IndexingWorkflow                     │   │
│  │  ┌────────────────────┐  ┌────────────────────────┐  │   │
│  │  │ configure_datasource│  │   execute_indexing     │  │   │
│  │  │     (Activity)      │  │     (Activity)         │  │   │
│  │  └────────────────────┘  └────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Your Connector (SDK)                     │   │
│  │  BaseDatasourceConnector → Glean Indexing API         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

### 1. Temporal Cluster

For development:
```bash
# Using Temporal CLI (recommended for local dev)
brew install temporal
temporal server start-dev

# Or using Docker Compose
git clone https://github.com/temporalio/docker-compose.git
cd docker-compose
docker compose up
```

For production, see [Temporal Cloud](https://temporal.io/cloud) or [self-hosting docs](https://docs.temporal.io/self-hosted-guide).

### 2. Python SDK

```bash
pip install temporalio>=1.7.0
```

## Examples

### [basic_workflow](./basic_workflow/)

The core pattern for running a connector as a Temporal workflow:

- **Workflow**: Orchestrates the two-step process
- **Activity 1**: Configure datasource in Glean
- **Activity 2**: Execute indexing with retry policy

### [scheduled_workflow](./scheduled_workflow/)

Adds Temporal Schedules for cron-like execution:

- Daily full syncs
- Hourly incremental syncs
- Custom schedule expressions

## Key Concepts

### Workflows vs Activities

| Concept | Purpose | Example |
|---------|---------|---------|
| **Workflow** | Orchestration logic (deterministic) | `IndexingWorkflow.run()` |
| **Activity** | Actual work (can fail, be retried) | `execute_indexing()` |

### Retry Policies

Activities can have configurable retry behavior:

```python
retry_policy = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)
```

### Timeouts

Set appropriate timeouts based on your data volume:

```python
await workflow.execute_activity(
    execute_indexing,
    start_to_close_timeout=timedelta(hours=2),  # Adjust for your dataset size
)
```

## Deployment Options

| Environment | Setup |
|-------------|-------|
| **Local Dev** | `temporal server start-dev` |
| **Docker** | Use provided docker-compose |
| **Kubernetes** | Temporal Helm charts |
| **Temporal Cloud** | Managed service (recommended for production) |

## Next Steps

1. Start with [basic_workflow](./basic_workflow/) to understand the pattern
2. Add scheduling with [scheduled_workflow](./scheduled_workflow/)
3. For multiple connectors, extend the pattern with dynamic workflow selection
