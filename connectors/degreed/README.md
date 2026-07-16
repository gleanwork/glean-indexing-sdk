# Degreed connector

This connector performs a full crawl of organization-visible Degreed catalog content and pushes it to Glean. Restricted content, pathways, skill plans, users, and learning activity are not included.

## Degreed setup

Create an organization OAuth API key with the minimum `content:read` scope. Provider-scoped keys may omit catalog records not owned by that provider.

## Required environment variables

```bash
export DEGREED_CLIENT_ID="..."
export DEGREED_CLIENT_SECRET="..."
export GLEAN_SERVER_URL="https://your-company-be.glean.com"
export GLEAN_INDEXING_API_TOKEN="..."
```

Optional overrides:

```bash
export DEGREED_API_BASE_URL="https://api.degreed.com"
export DEGREED_OAUTH_TOKEN_URL="https://degreed.com/oauth/token"
export DEGREED_ORGANIZATION_CODE="tenant-organization-code"
```

`DEGREED_ORGANIZATION_CODE` is needed only for Global Admin Tool organizations targeting a tenant organization. Use the documented regional API and OAuth URLs for EU, CA, or betatest deployments.

## Run

```bash
python -m connectors.degreed
```

The command configures the `degreed` datasource and replaces its full document set. Run it as a scheduled job only after validating a bounded source crawl and sample upload against test environments.

## Test

```bash
uv run pytest tests/unit_tests/connectors/test_degreed_connector.py -q
```

Planning and API exploration artifacts are under `.glean/`. No live Degreed API probes were performed during generation, so production response shapes and rate-limit behavior should be verified before deployment.
