---
name: connector-pull
description: Implement source-side pull logic for Glean Indexing SDK connectors. Use after API exploration when writing data clients that fetch from third-party APIs.
---

# Connector Pull

Use this skill when implementing source API fetching for a connector after `<connector-folder>/.glean/api_endpoints.json` and `<connector-folder>/.glean/source_investigation.md` are complete.

## Inputs

- `<connector-folder>/.glean/api_endpoints.json`
- `<connector-folder>/.glean/api_inventory.md`
- `<connector-folder>/.glean/source_investigation.md`
- `<connector-folder>/.glean/connector_plan.md`

## Rules

- Implement full-crawl source fetching for the AI-built connector. Do not implement incremental crawl unless the user explicitly asks for developer-owned follow-up work.
- A full crawl must enumerate the complete current set of in-scope items every run, so source-side removals are reflected (an item absent from the crawl gets pruned by stale-document deletion downstream). When the source exposes deletions or edits only as events (e.g. a compliance/audit/event feed), reconcile them inside the crawl — for example, collect deleted ids in a pass and skip those in the document stream ("created minus deleted" over the window), and use the latest event's content for edits. Never leave deletions or edits for a future incremental crawl to fix.
- Streaming and full crawl are compatible: use streaming/pagination to limit memory while still crawling all in-scope source data. Do not confuse streaming with incremental sync.
- Use source API behavior proven by API exploration. Do not invent pagination, rate-limit, auth, or response fields.
- Keep source fetching in the data client. Keep Glean mapping in the connector.
- When documents are permission-trimmed, the data client must also be able to enumerate the ACL members for each in-scope container (e.g. a memberships endpoint), and should cache those lookups per crawl. The push layer needs this to index ACL identities *before* documents; expose it (for example, a method that returns the union of ACL users) rather than only yielding documents.
- Use SDK pull recipes only. Inherit from the pull base classes and do not hand-roll ad hoc HTTP clients in generated connector code.
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
5. Choose and record source page size/max-items behavior from API limits and the confirmed plan.
6. Apply source API rate limits using `TokenBucketRateLimiter` when limits are known.
7. Use retry options for 429 and transient 5xx failures.
8. Preserve raw source IDs and URLs needed by the push/mapping layer.
9. Do not add unit tests until the full-crawl E2E smoke path is confirmed. Before that, use compile checks and a small dry-run/smoke run.

## Load And Crawl Frequency

Use the load and crawl-frequency decisions from `<connector-folder>/.glean/connector_plan.md`. If the plan is missing those decisions, return to the top-level `connector-builder` planning step instead of asking again here.
