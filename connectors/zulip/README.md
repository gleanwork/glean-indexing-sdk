# Zulip connector

This connector performs a full crawl of accessible Zulip channel messages and pushes them to Glean. Direct messages, archived channels, and incremental synchronization are not included.

## Required environment variables

```bash
export ZULIP_SITE="https://your-org.zulipchat.com"
export ZULIP_EMAIL="glean-connector-bot@your-org.example"
export ZULIP_API_KEY="..."
export GLEAN_SERVER_URL="https://your-company-be.glean.com"
export GLEAN_INDEXING_API_TOKEN="..."
```

Use a dedicated Zulip account that can access every intended channel and its historical messages. Private channels are indexed only when each active human subscriber has a visible `delivery_email`; otherwise, the crawl fails closed.

## Run

```bash
python -m connectors.zulip
```

The command configures the `zulip` datasource, uploads users and private-channel ACL groups, then replaces the full document set. Run it as a scheduled job only after validating a bounded crawl against a test Glean datasource.

## Test

```bash
pytest tests/unit_tests/connectors/test_zulip_connector.py -q
```

Planning and API exploration artifacts are under `.glean/`. They document the docs-only confidence gaps and required pre-production checks.
