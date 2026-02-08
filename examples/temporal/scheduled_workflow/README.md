# Scheduled Temporal Workflow Example

This example extends the basic workflow with Temporal Schedules for cron-like execution.

## Overview

Temporal Schedules provide built-in scheduling capabilities:

- **Cron expressions** - Familiar syntax for scheduling
- **Durable scheduling** - Schedules survive cluster restarts
- **Backfill support** - Catch up on missed executions
- **Pause/resume** - Easily pause schedules without deleting them

## Project Structure

```
scheduled_workflow/
  src/scheduled_workflow/
    __init__.py
    connector.py    # Sample connector
    activities.py   # Temporal activities
    workflow.py     # Workflow definition
    worker.py       # Worker process
    schedule.py     # Schedule management CLI
  pyproject.toml
  .env.example
  README.md
```

## Prerequisites

1. **Temporal Cluster** with schedule support:
   ```bash
   temporal server start-dev
   ```

2. **Python 3.10+**

## Setup

1. Install the example:
   ```bash
   cd examples/temporal/scheduled_workflow
   pip install -e .
   ```

2. Create environment file:
   ```bash
   cp .env.example .env
   ```

## Running

### Terminal 1: Start the Worker

```bash
python -m scheduled_workflow.worker
```

### Terminal 2: Create a Schedule

```bash
# Daily full sync at 2 AM
python -m scheduled_workflow.schedule create sample_docs \
    --schedule-id daily-sample-sync \
    --cron "0 2 * * *" \
    --mode FULL

# Hourly incremental sync
python -m scheduled_workflow.schedule create sample_docs \
    --schedule-id hourly-sample-sync \
    --cron "0 * * * *" \
    --mode INCREMENTAL
```

### List and Manage Schedules

```bash
# List all schedules
python -m scheduled_workflow.schedule list

# Delete a schedule
python -m scheduled_workflow.schedule delete daily-sample-sync
```

## Common Cron Expressions

| Expression | Description |
|------------|-------------|
| `0 2 * * *` | Daily at 2 AM |
| `0 * * * *` | Every hour |
| `0 */4 * * *` | Every 4 hours |
| `0 2 * * 0` | Weekly on Sunday at 2 AM |
| `0 2 1 * *` | Monthly on the 1st at 2 AM |

## Schedule Patterns

### Daily Full Sync + Hourly Incremental

A common pattern for production:

```bash
# Nightly full sync
python -m scheduled_workflow.schedule create my_connector \
    --schedule-id nightly-full-sync \
    --cron "0 2 * * *" \
    --mode FULL

# Hourly incremental during business hours
python -m scheduled_workflow.schedule create my_connector \
    --schedule-id hourly-incremental \
    --cron "0 9-17 * * 1-5" \
    --mode INCREMENTAL
```

### Monitoring

View schedules in the Temporal UI:
- http://localhost:8233/namespaces/default/schedules

The UI shows:
- Next scheduled run
- Recent executions
- Paused state

## Customization

### Using Your Own Connector

Replace `connector.py` with your actual connector:

```python
from your_package import YourConnector, YourDataClient

def create_connector(connector_name: str) -> YourConnector:
    data_client = YourDataClient(...)
    return YourConnector(name=connector_name, data_client=data_client)
```

### Adding More Schedules Programmatically

```python
from scheduled_workflow.schedule import create_schedule

# Create multiple schedules
connectors = ["wiki", "confluence", "notion"]
for connector in connectors:
    await create_schedule(
        connector_name=connector,
        schedule_id=f"daily-{connector}",
        cron_expression="0 2 * * *",
        mode="FULL",
    )
```

## Next Steps

- Deploy workers to Kubernetes for production
- Use Temporal Cloud for managed infrastructure
- Add monitoring with Temporal's built-in metrics
