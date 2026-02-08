# AWS Lambda Example

Run a Glean connector as an AWS Lambda function with EventBridge scheduling.

## Overview

This example deploys a connector to AWS Lambda with:

- **EventBridge Schedules** - Daily full sync and hourly incremental sync
- **SAM Template** - Infrastructure as code for easy deployment
- **CloudWatch Logs** - Automatic logging with retention

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AWS Cloud                                 │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │  EventBridge │      │  EventBridge │                     │
│  │  Rule        │      │  Rule        │                     │
│  │  (2 AM UTC)  │      │  (Hourly)    │                     │
│  └──────┬───────┘      └──────┬───────┘                     │
│         │                      │                             │
│         │    {"mode":"FULL"}   │   {"mode":"INCREMENTAL"}   │
│         │                      │                             │
│         └──────────┬───────────┘                             │
│                    │                                         │
│                    ▼                                         │
│         ┌──────────────────┐                                │
│         │  Lambda Function │                                │
│         │  ┌────────────┐  │                                │
│         │  │ Connector  │  │─────────────► Glean API        │
│         │  │ (SDK)      │  │                                │
│         │  └────────────┘  │                                │
│         └──────────────────┘                                │
│                    │                                         │
│                    ▼                                         │
│         ┌──────────────────┐                                │
│         │  CloudWatch Logs │                                │
│         └──────────────────┘                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS SAM CLI** installed:
   ```bash
   pip install aws-sam-cli
   ```
3. **Python 3.10+**

## Project Structure

```
aws_lambda/
  src/lambda_handler/
    __init__.py
    connector.py    # Your connector implementation
    handler.py      # Lambda handler
  template.yaml     # SAM template
  pyproject.toml
  README.md
```

## Local Development

### Install Dependencies

```bash
pip install -e .
```

### Test Locally with SAM

```bash
# Build the function
sam build

# Invoke locally
sam local invoke ConnectorFunction \
    --event events/full_sync.json \
    --env-vars env.json
```

Create `events/full_sync.json`:
```json
{
  "mode": "FULL",
  "configure": true
}
```

Create `env.json`:
```json
{
  "ConnectorFunction": {
    "GLEAN_INSTANCE": "your-instance",
    "GLEAN_INDEXING_API_TOKEN": "your-token",
    "SOURCE_API_URL": "https://docs.company.com",
    "SOURCE_API_KEY": "your-source-key"
  }
}
```

## Deployment

### Deploy with SAM

```bash
# Build
sam build

# Deploy (guided first time)
sam deploy --guided

# Subsequent deploys
sam deploy
```

### Required Parameters

During deployment, you'll be prompted for:

| Parameter | Description |
|-----------|-------------|
| `GleanInstance` | Your Glean instance name |
| `GleanApiToken` | Glean Indexing API token |
| `SourceApiUrl` | Your source system API URL |
| `SourceApiKey` | Your source system API key |

## Scheduling

The SAM template configures two schedules:

| Schedule | Cron Expression | Mode | Description |
|----------|-----------------|------|-------------|
| Daily Full | `cron(0 2 * * ? *)` | FULL | 2 AM UTC daily |
| Hourly Incremental | `cron(0 9-17 ? * MON-FRI *)` | INCREMENTAL | Business hours |

### Modify Schedules

Edit `template.yaml` to change schedules:

```yaml
DailyFullSync:
  Type: Schedule
  Properties:
    Schedule: cron(0 4 * * ? *)  # Changed to 4 AM
```

## Limitations

- **15-minute timeout** - Lambda maximum execution time
- **Memory/CPU limits** - May need adjustment for large datasets
- **No durable state** - Consider DynamoDB for incremental sync timestamps

### Handling Large Datasets

For datasets that exceed Lambda's 15-minute limit:

1. **Chunked processing** - Process data in batches across multiple invocations
2. **Step Functions** - Orchestrate multiple Lambda invocations
3. **Consider Temporal** - For very large or complex syncs

## Customization

### Using Your Own Connector

Replace `connector.py` with your actual connector:

```python
from your_package import YourConnector, YourDataClient

class SampleDataClient(YourDataClient):
    # Your implementation
    pass

class SampleConnector(YourConnector):
    # Your implementation
    pass
```

### Adding More Environment Variables

Update `template.yaml`:

```yaml
Environment:
  Variables:
    MY_CUSTOM_VAR: !Ref MyCustomParameter
```

## Monitoring

### CloudWatch Logs

View logs in the AWS Console or CLI:

```bash
sam logs -n ConnectorFunction --stack-name your-stack-name --tail
```

### Metrics

Lambda automatically provides metrics:
- Invocations
- Duration
- Errors
- Throttles

## Cleanup

```bash
sam delete --stack-name your-stack-name
```
