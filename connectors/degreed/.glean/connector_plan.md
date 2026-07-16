# Degreed connector plan

Status: confirmed

## Product scope

- Entity scope: all non-obsolete, organization-visible Degreed catalog learning content.
- Excluded from version 1: restricted content, pathways, skill plans, users, completions, required learning, accomplishments, and source writes.
- Crawl mode: full crawl only. Incremental crawling using `filter[modified_after]` is a developer-owned follow-up because updates alone do not provide a complete deletion signal.
- SDK usage: full connector flow using SDK pull recipes, document transformation, and SDK push/status wrappers.

## Source endpoints

1. `POST https://degreed.com/oauth/token`
   - Obtain an OAuth bearer token using client credentials and `content:read`.
2. `GET https://api.degreed.com/api/v2/content?limit=1000`
   - Fetch all non-obsolete organization-visible content.
   - Follow `links.next` immediately until pagination completes.
3. `GET https://api.degreed.com/api/v2/content/{id}`
   - Optional debug verification only; not part of the normal crawl.

No request will set `filter[include_restricted]=true`.

## Authentication

- Test auth: No credentials supplied; API exploration was documentation-only.
- Production auth: OAuth 2.0 client credentials from `DEGREED_CLIENT_ID` and `DEGREED_CLIENT_SECRET`, with the bearer token cached only in memory.
- Optional configuration: `DEGREED_API_BASE_URL`, `DEGREED_OAUTH_TOKEN_URL`, and `DEGREED_ORGANIZATION_CODE`.
- Required source scope: `content:read`.
- Glean auth: `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`.

## Source-to-Glean mapping

Each Degreed `data[]` record becomes one Glean `DocumentDefinition`:

- `id`: Degreed content `id`.
- `title`: `attributes.title`; records without a non-empty title are skipped and counted.
- `view_url`: `attributes.degreed-url`, falling back to `attributes.url`.
- `body`: plain-text composition of summary, provider, content type, format, language, duration/learning minutes, and associated skills.
- `summary`: `attributes.summary` as plain text.
- `updated_at`: `modified-at`, falling back to `created-at`.
- `created_at`: `created-at`.
- `custom properties`: content type, external ID, provider, language, learning minutes, internal/external flag, publication date, source URL, and skills.
- Permissions: datasource-wide visibility only because restricted content is excluded.

The implementation will preserve nullable fields safely, skip and count records missing an ID, title, or view URL, and will not fetch type-specific detail endpoints per record.

## Pull implementation

- Use `BasePullHttpStreamingDataClient`, `PullHttpClient`, `PullOptions`, and `PullRetryOptions` from `glean.indexing.recipes.pull`.
- Implement Degreed's `links.next` cursor behavior without inventing unsupported offset pagination.
- Page size: 1,000.
- Retry `429` and transient `5xx` responses, honor `Retry-After`, and use bounded exponential backoff.
- Do not log authorization headers, client credentials, token responses, or content bodies.
- Fail the crawl if pagination cannot complete; do not finalize a partial upload.

## Glean push implementation

- Configure the custom datasource with `PushUploader.configure_datasource`.
- Upload a successful full crawl with `PushUploader.bulk_index_documents`.
- Use a small `PushUploader.index_documents` call only for an explicitly requested test upload.
- Full-crawl replacement provides stale-document cleanup for content no longer returned by Degreed.
- After a credentialed test run, use `StatusClient.get_datasource_status` and `StatusClient.get_documents_status` for sampled records. Use `PushUploader.get_document_lifecycle_events` only to debug failed samples.

## Observability

- Provider: `ConsoleLoggerProvider` plus `NoOpMetricsProvider` by default; `InMemoryMetricsProvider` in tests.
- Use one `ConnectorObservability` instance through pull, transform, and `PushUploader`.
- Lifecycle logs: crawl started, completed, and failed.
- Fetch signals: page/request count, fetched item count, elapsed time, retry count, and failures.
- Transform signals: input, output, skipped-title, and malformed-record counts plus duration.
- Upload signals: batch count, document count, batch size, upload ID, completion, and failure.
- Evaluation signals: datasource status and sampled document status.
- Redaction: no source credentials, bearer tokens, Glean tokens, authorization headers, request bodies, or customer summaries in logs.

## Load, schedule, and hosting assumptions

- Expected document count: unknown; design for at least hundreds of thousands using streaming and bounded batches.
- Average document size: unknown; expected to be small metadata/summary documents rather than full binary content.
- Freshness target: daily.
- Recommended crawl frequency: one full crawl every 24 hours, adjustable after measuring catalog size and crawl duration.
- Source API limits: numeric limit unknown; maximum documented page size is 1,000 and pagination cursors expire after two minutes of inactivity.
- Hosting: a customer-managed Python 3.10+ scheduled job or container with network access to Degreed and Glean.
- Deployment owner: customer connector operator.

## Validation and tests

1. Run the connector-builder artifact validator after this plan is confirmed.
2. Unit-test OAuth token exchange, token reuse/expiry, pagination, full next URLs, missing next links, retries, nullable attributes, mapping, and skipped malformed records.
3. Compile and lint the connector.
4. Run mocked end-to-end source-to-Glean tests without network access.
5. When Degreed credentials are available, fetch a small page and verify response shape without persisting customer content.
6. When Glean test credentials are available, upload a small sample and check datasource/document status.

## Prerequisite branch dependency

This branch is based on `origin/feature/v0-workstream`, which supplies the validator and SDK pull/push wrappers required by the connector workflow. The connector uses those shared SDK APIs rather than copying their internals.
