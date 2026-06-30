---
name: connector-pull
description: Implement source-side pull logic for Glean Indexing SDK connectors. Use after API exploration when writing data clients that fetch from third-party APIs.
---

# Connector Pull

Use this skill when implementing source API fetching for a connector after `.glean/api_endpoints.json` and `.glean/source_investigation.md` are complete.

## Inputs

- `.glean/api_endpoints.json`
- `.glean/api_inventory.md`
- `.glean/source_investigation.md`
- `.glean/connector_plan.md`

## Rules

- Implement full-crawl source fetching for the AI-built connector. Do not implement incremental crawl unless the user explicitly asks for developer-owned follow-up work.
- Use source API behavior proven by API exploration. Do not invent pagination, rate-limit, auth, or response fields.
- Keep source fetching in the data client. Keep Glean mapping in the connector.
- Prefer SDK pull recipes over ad hoc HTTP code when they fit.
- Redact secrets in logs and examples.

## SDK Pull Surface

Use these SDK exports from `glean.indexing.recipes.pull`:

- `PullHttpClient`: source-side HTTP client for GET/POST, retries, response parsing, and redacted request logging.
- `BasePullHttpStreamingDataClient`: streaming data client for common list endpoints.
- `PullOptions` and `PullRetryOptions`: timeouts, retries, retry-after handling, and parameter masking.
- `TokenBucketRateLimiter`: source API rate limiting.
- `PullPaginationMode`: `link`, `offset`, `cursor`, or `none`.
- `PullResponse`: parsed JSON/list response helper.

## Implementation Flow

1. Read the confirmed endpoint inventory and source investigation.
2. Choose the simplest full-crawl data model that satisfies the confirmed plan.
3. Implement one source data shape per source entity.
4. Implement list/detail fetching with the pagination mode documented during API exploration.
5. Apply source API rate limits using `TokenBucketRateLimiter` when limits are known.
6. Use retry options for 429 and transient 5xx failures.
7. Preserve raw source IDs and URLs needed by the push/mapping layer.
8. Add minimal local checks using sample data or mocked HTTP responses when possible.

## Load And Crawl Frequency Inputs

Ask the user for:

- Expected number of documents.
- Average document size or attachment size.
- Expected change rate.
- Source API rate limits.
- Freshness requirement.
- Whether Glean or the customer will host the crawl.

Use those inputs to recommend a full-crawl frequency. Since the AI layer currently supports full crawl only, call out when the expected load or freshness requirement suggests that a developer should design incremental crawl support.
