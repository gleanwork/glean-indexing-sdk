# Docker Container Example

Run a Glean connector as a Docker container.

## Overview

This example provides:

- **Multi-stage Dockerfile** - Minimal image with security best practices
- **docker-compose** - Easy local development and testing
- **CLI arguments** - Flexible execution modes

## Project Structure

```
docker/
  src/connector/
    __init__.py
    sample_connector.py   # Your connector implementation
    main.py               # CLI entry point
  Dockerfile
  docker-compose.yml
  .dockerignore
  .env.example
  pyproject.toml
  README.md
```

## Prerequisites

- Docker and Docker Compose
- Glean API credentials

## Quick Start

### 1. Setup Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Build the Image

```bash
docker build -t glean-connector .
```

### 3. Run the Connector

```bash
# Full sync
docker run --env-file .env glean-connector --mode FULL

# Incremental sync
docker run --env-file .env glean-connector --mode INCREMENTAL

# With datasource configuration
docker run --env-file .env glean-connector --configure --mode FULL

# Dry run (no upload)
docker run --env-file .env glean-connector --dry-run
```

### Using Docker Compose

```bash
# Build and run
docker-compose up --build

# Run with different mode
docker-compose run connector --mode INCREMENTAL
```

## Dockerfile Features

### Multi-stage Build

The Dockerfile uses a multi-stage build for minimal image size:

```dockerfile
# Stage 1: Build the wheel
FROM python:3.11-slim as builder
...

# Stage 2: Runtime (only includes built package)
FROM python:3.11-slim
...
```

### Security

- **Non-root user** - Container runs as `appuser`
- **Minimal base image** - `python:3.11-slim`
- **No unnecessary files** - `.dockerignore` excludes dev files

### Image Size

Typical image size: ~150MB (compared to ~1GB for full Python images)

## CLI Options

```
usage: python -m connector.main [-h] [--mode {FULL,INCREMENTAL}] [--configure] [--dry-run]

options:
  --mode {FULL,INCREMENTAL}   Indexing mode (default: FULL)
  --configure                 Configure datasource before indexing
  --dry-run                   Fetch and transform data without uploading
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GLEAN_INSTANCE` | Glean instance name | Yes |
| `GLEAN_INDEXING_API_TOKEN` | Glean API token | Yes |
| `SOURCE_API_URL` | Source system URL | No |
| `SOURCE_API_KEY` | Source system API key | No |

## Scheduling

### Option 1: Host Cron

Add to host's crontab:

```bash
# Daily full sync at 2 AM
0 2 * * * docker run --rm --env-file /path/to/.env glean-connector --mode FULL

# Hourly incremental sync
0 * * * * docker run --rm --env-file /path/to/.env glean-connector --mode INCREMENTAL
```

### Option 2: Kubernetes CronJob

See the [kubernetes example](../kubernetes/) for K8s-native scheduling.

### Option 3: Container Orchestration

Use Docker Swarm, ECS, or other orchestrators with their scheduling features.

## Customization

### Using Your Own Connector

Replace `sample_connector.py` with your actual connector:

```python
from your_package import YourConnector, YourDataClient

class SampleDataClient(YourDataClient):
    # Your implementation
    pass

class SampleConnector(YourConnector):
    # Your implementation
    pass
```

### Adding Dependencies

Update `pyproject.toml`:

```toml
dependencies = [
    "glean-indexing-sdk>=0.2.0",
    "your-dependency>=1.0.0",
]
```

Rebuild the image:

```bash
docker build -t glean-connector .
```

### Custom Base Image

If you need additional system packages:

```dockerfile
FROM python:3.11-slim as builder
...

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    your-package \
    && rm -rf /var/lib/apt/lists/*
...
```

## Debugging

### View Logs

```bash
docker logs <container-id>
```

### Interactive Shell

```bash
docker run -it --env-file .env glean-connector /bin/bash
```

### Test Locally

```bash
pip install -e .
python -m connector.main --dry-run
```

## Production Considerations

1. **Image Registry** - Push to a private registry
2. **Secret Management** - Use Docker secrets or external secret manager
3. **Resource Limits** - Set memory and CPU limits
4. **Health Checks** - Add container health checks
5. **Logging** - Configure log aggregation

## Next Steps

- Deploy to Kubernetes with [kubernetes example](../kubernetes/)
- Add monitoring with Prometheus metrics
- Set up CI/CD for automated builds
