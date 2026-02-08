# Basic Temporal Workflow Example

A minimal example showing how to run a Glean connector as a Temporal workflow.

## Overview

This example demonstrates the core Temporal pattern for connector execution:

1. **Workflow** (`workflow.py`) - Orchestrates the two-step process
2. **Activities** (`activities.py`) - The actual work (configure + index)
3. **Worker** (`worker.py`) - Long-running process that executes workflows
4. **Starter** (`starter.py`) - Script to trigger workflow execution

## Architecture

```
                    ┌─────────────────┐
                    │  Temporal       │
                    │  Cluster        │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              │              ▼
    ┌─────────────────┐      │    ┌─────────────────┐
    │  starter.py     │      │    │  Temporal UI    │
    │  (trigger)      │──────┘    │  (monitor)      │
    └─────────────────┘           └─────────────────┘
                                          │
                                          ▼
                               ┌─────────────────┐
                               │  worker.py      │
                               │  ┌───────────┐  │
                               │  │ Workflow  │  │
                               │  │ Activities│  │
                               │  └───────────┘  │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  Glean API      │
                               └─────────────────┘
```

## Prerequisites

1. **Temporal Cluster** (local development):
   ```bash
   # Using Temporal CLI
   brew install temporal
   temporal server start-dev
   ```

2. **Python 3.10+**

## Setup

1. Install the example:
   ```bash
   cd examples/temporal/basic_workflow
   pip install -e .
   ```

2. Create environment file:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Running

### Terminal 1: Start the Worker

```bash
python -m basic_workflow.worker
```

You should see:
```
Connecting to Temporal at localhost:7233 (namespace: default)
Starting worker on task queue: glean-indexing-queue
```

### Terminal 2: Start a Workflow

```bash
# Run a full sync
python -m basic_workflow.starter sample_docs

# Run an incremental sync
python -m basic_workflow.starter sample_docs --mode INCREMENTAL

# Skip configuration step
python -m basic_workflow.starter sample_docs --skip-config
```

### Monitor in Temporal UI

Open http://localhost:8233 to see:
- Workflow execution history
- Activity retries and timing
- Input/output data

## Project Structure

```
basic_workflow/
  src/basic_workflow/
    __init__.py
    connector.py    # Sample connector (replace with your own)
    activities.py   # Temporal activities
    workflow.py     # Workflow definition
    worker.py       # Worker process
    starter.py      # CLI to start workflows
  pyproject.toml
  .env.example
  README.md
```

## Key Patterns

### Retry Policy

The workflow configures retry policies for each activity:

```python
retry_policy = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
)
```

### Timeouts

Set appropriate timeouts based on your data volume:

```python
start_to_close_timeout=timedelta(hours=2),  # For large datasets
```

### Workflow Input

Use a dataclass for type-safe workflow parameters:

```python
@dataclass
class IndexingWorkflowInput:
    connector_name: str
    mode: str = "FULL"
    skip_configuration: bool = False
```

## Customization

### Using Your Own Connector

Replace `connector.py` with your actual connector implementation:

```python
# connector.py
from your_package import YourConnector, YourDataClient

def create_connector(connector_name: str) -> YourConnector:
    data_client = YourDataClient(...)
    return YourConnector(name=connector_name, data_client=data_client)
```

### Adjusting Timeouts

For large datasets, increase the activity timeout:

```python
start_to_close_timeout=timedelta(hours=4),  # 4 hours for very large datasets
```

## Next Steps

- Add scheduling with [scheduled_workflow](../scheduled_workflow/)
- Deploy workers to Kubernetes
- Use Temporal Cloud for production
