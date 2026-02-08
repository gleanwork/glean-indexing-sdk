# Glean Indexing SDK Examples

This directory contains comprehensive examples showing how to deploy and run Glean connectors in production environments.

## Quick Start

If you're new to the SDK, start with the [simple wiki connector](./simple/wiki_connector/) example to understand the basic patterns.

## Examples by Deployment Type

### Simple (Getting Started)

| Example | Description |
|---------|-------------|
| [wiki_connector](./simple/wiki_connector/) | Minimal standalone connector - great for learning the SDK basics |

### Temporal Workflows (Recommended for Production)

Temporal provides durable execution with automatic retries, scheduling, and observability. This is the recommended approach for production connector deployments.

| Example | Description |
|---------|-------------|
| [basic_workflow](./temporal/basic_workflow/) | Core pattern: configure datasource + execute indexing as Temporal activities |
| [scheduled_workflow](./temporal/scheduled_workflow/) | Cron-like scheduling using Temporal Schedules |

See [temporal/README.md](./temporal/README.md) for concepts and prerequisites.

### Serverless

For lightweight, event-driven connector execution.

| Example | Description |
|---------|-------------|
| [aws_lambda](./serverless/aws_lambda/) | AWS Lambda with EventBridge scheduled rules |
| [cloudflare_workers](./serverless/cloudflare_workers/) | Cloudflare Workers with Cron Triggers |

### Containers

For containerized deployments with various orchestration options.

| Example | Description |
|---------|-------------|
| [docker](./containers/docker/) | Dockerfile with docker-compose for local development |
| [kubernetes](./containers/kubernetes/) | Kubernetes CronJob for scheduled execution |

## Choosing the Right Approach

| Approach | Best For | Trade-offs |
|----------|----------|------------|
| **Temporal** | Production workloads, large datasets, complex orchestration | Requires Temporal cluster |
| **AWS Lambda** | Small-medium datasets, infrequent syncs | 15-minute timeout limit |
| **Cloudflare Workers** | Small datasets, edge execution | CPU time limits |
| **Kubernetes CronJob** | Existing K8s infrastructure | Requires cluster management |
| **Docker** | Local development, simple deployments | No built-in scheduling |

## Common Patterns

All examples follow the same core pattern:

```python
from glean.indexing.connectors import BaseDatasourceConnector
from glean.indexing.models import IndexingMode

# 1. Create your data client
data_client = MyDataClient(api_url="...", api_key="...")

# 2. Initialize your connector
connector = MyConnector(name="my_datasource", data_client=data_client)

# 3. Configure the datasource in Glean (run once or on schema changes)
connector.configure_datasource()

# 4. Index data
connector.index_data(mode=IndexingMode.FULL)  # or IndexingMode.INCREMENTAL
```

The examples differ in HOW this code is orchestrated and scheduled.

## Environment Variables

All examples require these environment variables:

```bash
GLEAN_INSTANCE="your-instance"           # e.g., "acme"
GLEAN_INDEXING_API_TOKEN="your-token"    # Glean API token for indexing
```

## Running Examples

Each example is self-contained with its own `pyproject.toml`. To run an example:

```bash
cd examples/<category>/<example>
pip install -e .
# Follow the example's README for specific instructions
```
