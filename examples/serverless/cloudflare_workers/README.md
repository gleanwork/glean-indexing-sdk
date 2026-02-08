# Cloudflare Workers Example

Run a Glean connector using Cloudflare Workers with Cron Triggers.

## Overview

This example demonstrates two approaches:

1. **Orchestrator** - Worker triggers a backend service running the Python connector
2. **Direct API** - Worker makes Glean API calls directly (for simple use cases)

## Architecture

### Approach 1: Backend Orchestrator (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│                  Cloudflare Edge                             │
│                                                              │
│  ┌──────────────┐                                           │
│  │ Cron Trigger │                                           │
│  │ (2 AM UTC)   │                                           │
│  └──────┬───────┘                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │   Worker     │                                           │
│  │ (Orchestrator│───────────────────────────┐               │
│  └──────────────┘                           │               │
│                                             │               │
└─────────────────────────────────────────────│───────────────┘
                                              │
                                              ▼
                                   ┌──────────────────┐
                                   │  Backend Service │
                                   │  (Python SDK)    │
                                   │                  │
                                   │  ┌────────────┐  │
                                   │  │ Connector  │──┼──► Glean API
                                   │  └────────────┘  │
                                   └──────────────────┘
```

### Approach 2: Direct API Calls

```
┌─────────────────────────────────────────────────────────────┐
│                  Cloudflare Edge                             │
│                                                              │
│  ┌──────────────┐                                           │
│  │ Cron Trigger │                                           │
│  └──────┬───────┘                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │   Worker     │────────────────────────────► Glean API    │
│  │ (Direct API) │                                           │
│  └──────────────┘                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Cloudflare account** with Workers enabled
2. **Wrangler CLI**:
   ```bash
   npm install -g wrangler
   wrangler login
   ```

## Project Structure

```
cloudflare_workers/
  src/
    index.ts        # Worker entry point
  package.json
  wrangler.toml     # Worker configuration
  tsconfig.json
  README.md
```

## Setup

### Install Dependencies

```bash
npm install
```

### Configure Secrets

```bash
# Required: Glean credentials
wrangler secret put GLEAN_INSTANCE
wrangler secret put GLEAN_INDEXING_API_TOKEN

# Optional: Backend service URL (for orchestrator approach)
wrangler secret put CONNECTOR_API_URL
```

## Local Development

```bash
npm run dev
```

Test endpoints:

```bash
# Health check
curl http://localhost:8787/health

# Manual trigger (full sync)
curl -X POST http://localhost:8787/trigger \
  -H "Content-Type: application/json" \
  -d '{"mode": "FULL"}'

# Manual trigger (incremental sync)
curl -X POST http://localhost:8787/trigger \
  -H "Content-Type: application/json" \
  -d '{"mode": "INCREMENTAL"}'
```

## Deployment

```bash
npm run deploy
```

## Scheduling

The Worker is configured with Cron Triggers in `wrangler.toml`:

```toml
[triggers]
crons = [
  "0 2 * * *",    # Daily full sync at 2 AM UTC
  "0 * * * *"     # Hourly incremental sync
]
```

The Worker automatically determines the mode based on the trigger time:
- 2 AM UTC = FULL sync
- Other hours = INCREMENTAL sync

### Modify Schedules

Edit `wrangler.toml`:

```toml
[triggers]
crons = [
  "0 4 * * *",    # Changed to 4 AM UTC
]
```

## Choosing an Approach

### Use Backend Orchestrator When:
- Large datasets that exceed Worker CPU limits
- Complex data transformations
- You need the full Python SDK capabilities
- Connector requires database access

### Use Direct API When:
- Small datasets (< 100 documents)
- Simple HTTP-accessible source data
- Quick proof-of-concept
- Minimal transformation needed

## Limitations

- **CPU time limits** - Workers have 10-50ms CPU time (paid plans: 30s)
- **Memory limits** - 128MB maximum
- **No persistent state** - Use KV or Durable Objects if needed

### Workarounds

1. **Backend service** - Offload heavy processing to a backend
2. **Batch processing** - Split large datasets across multiple invocations
3. **Durable Objects** - For stateful processing

## Monitoring

### View Logs

```bash
npm run tail
```

### Cloudflare Dashboard

View in the Cloudflare Dashboard:
- Workers & Pages > Your Worker > Logs

## Customization

### Adding More Endpoints

```typescript
// In handleFetch
if (url.pathname === "/custom-endpoint") {
  // Your custom logic
}
```

### Different Schedules per Connector

Create multiple Workers or use a single Worker with routing:

```typescript
async function handleScheduled(event: ScheduledEvent) {
  const hour = new Date(event.scheduledTime).getUTCHours();

  if (hour === 2) {
    await runConnectorA("FULL");
  } else if (hour === 3) {
    await runConnectorB("FULL");
  }
}
```

## Next Steps

- Deploy a backend service for heavy processing
- Add error alerting with Cloudflare Workers Analytics
- Use KV for incremental sync state management
