# Zulip connector plan

Status: confirmed

## Goal and confirmed first-version scope

Build a full-crawl connector that indexes channel messages visible to a dedicated Zulip principal. Include channel metadata, authors, and channel-level permissions. Exclude direct messages, attachments as separate documents, reactions, edit history, archived channels, and incremental synchronization.

## SDK usage

SDK usage: Full connector flow using SDK pull recipes for Zulip reads and SDK push wrappers for Glean datasource configuration, identity uploads, permission uploads, document uploads, and status checks.

## Source API usage

| Endpoint | Use |
| --- | --- |
| `GET /api/v1/streams` | Discover accessible, non-archived channels and privacy metadata. |
| `GET /api/v1/users` | Build datasource users and resolve message authors/member IDs. |
| `GET /api/v1/streams/{stream_id}/members` | Build private-channel groups and memberships. |
| `GET /api/v1/messages` | Crawl each channel oldest-to-newest in pages of at most 1,000 messages. |

The message loop uses a channel narrow, starts at `anchor=oldest`, and advances from the highest returned message ID until `found_newest=true`. It fails on non-advancing pages and reports `history_limited=true`.

Sources:
- https://zulip.com/api/get-streams
- https://zulip.com/api/get-users
- https://zulip.com/api/get-subscribers
- https://zulip.com/api/get-messages

## Authentication

- Test auth: Documentation-only exploration; no live Zulip credentials were provided.
- Production auth: HTTP Basic authentication using `ZULIP_EMAIL` and `ZULIP_API_KEY`, with the validated organization base URL in `ZULIP_SITE`.
- Glean auth: `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`.
- Secret policy: Mask authorization parameters and never log credentials, authorization headers, cookies, or message bodies.

The production Zulip principal must have content access to every intended channel, subscriber-list access for private channels, and sufficiently complete historical access.

## Source-to-Glean mapping

### Documents

One `DocumentDefinition` per Zulip channel message:

- ID: `zulip-message-{message_id}`
- Title: `#{channel_name} > {topic}`
- Body: rendered HTML message content
- URL: organization-host deep link to the source message; exact link format will be covered by unit tests
- Created time: message `timestamp`
- Updated time: `last_edit_timestamp` when present, otherwise `timestamp`
- Author: datasource user reference derived from `sender_id`
- Metadata/tags: channel name, topic, channel ID, sender name, and message type
- Permissions: datasource-wide for public channels; matching datasource channel group for private channels

Private-channel mapping must fail closed if channel privacy, members, or user identity mappings are unavailable.

### Identities and permissions

- Datasource users: active, non-bot Zulip users, keyed using a deterministic datasource user identifier derived from `user_id`; map a real email only when Zulip exposes one that can resolve in Glean.
- Datasource groups: one group named `zulip-channel-{stream_id}` per private channel.
- Memberships: each active subscriber of a private channel joins its corresponding group.
- Bots: retained as display-only message authors when no resolvable Glean identity exists; they do not receive access memberships.

Identity resolution for private content is a pre-production gate. The connector must not upload private documents until the target organization verifies user mapping.

## Pull implementation

- Use `PullHttpClient`, `PullOptions`, and `PullRetryOptions`.
- Use a source-side rate limiter only after a documented or observed limit is available.
- Retry 429 and transient 5xx responses, honoring `Retry-After`.
- Use explicit request timeouts and bounded message page sizes.
- Keep HTTP fetching in a Zulip data client and Glean mapping in the connector.
- Perform a full crawl only; do not persist an incremental cursor.

## Glean push implementation

Use `PushUploader` only:

1. `configure_datasource`
2. `bulk_index_users`
3. `bulk_index_groups`
4. `bulk_index_memberships`
5. `bulk_index_documents`

Use a shared upload/run identifier where supported. A test run may use `index_documents` with a small public-channel sample before the complete bulk upload.

After a credentialed test upload, use `StatusClient.get_datasource_status`, `StatusClient.get_documents_status`, and `StatusClient.check_document_access`. Use `PushUploader.get_document_lifecycle_events` and `PushUploader.debug_user` only when diagnosing failed evaluation checks.

## Full-crawl and stale-data behavior

Bulk replacement is authoritative for the records visible in a complete run. Removed/deleted messages, users, groups, and memberships disappear when absent from a later successful full crawl. The connector must not finalize replacement after a partial source crawl, permission failure, non-advancing page, or `history_limited` result that has not been explicitly accepted.

Incremental synchronization via Zulip's events API is a developer-owned follow-up because durable cursors, event expiry, replay, and deletion signals need separate design.

## Observability

- Provider: `ConsoleLoggerProvider` with `NoOpMetricsProvider` by default; `InMemoryMetricsProvider` in tests.
- Lifecycle logs: crawl started, each phase started/completed, crawl completed/failed.
- Fetch metrics: request count, duration, retries, channels/users/memberships/messages fetched, page count, and `history_limited` occurrences.
- Transform metrics: input, output, skipped, unresolved-author, and private-permission failure counts.
- Upload metrics: entity type, batch size, batch duration, upload ID, success, and failure.
- Evaluation logs: datasource status, sampled document status, and public/private access-check outcomes.
- Redaction: no credentials, authorization values, cookies, or customer message content in logs.

Pass the same `ConnectorObservability` instance into source fetching and `PushUploader`.

## Testing and evaluation

Credential-free checks:

- Unit-test Basic auth construction without exposing secrets.
- Mock users, public/private channels, memberships, and multi-page messages.
- Test pagination termination and non-advancing-page protection.
- Test document IDs, title/body/timestamps, author mapping, and deep links.
- Test public permissions and fail-closed private permissions.
- Test deactivated users, bots, missing users, archived channels, retries, and `history_limited`.
- Compile, lint, type-check, and run focused tests.

Credentialed pre-production checks:

- Probe all four source endpoints against the target Zulip version.
- Run a bounded crawl and compare counts with Zulip.
- Verify complete intended history and private-channel membership visibility.
- Upload a public sample, then a private sample after identity validation.
- Check allow/deny access using representative members and non-members.
- Inspect Glean processing status and lifecycle events.

## Capacity, freshness, and deployment

- Expected document count: Unknown until the first source probe; approximately one document per accessible channel message.
- Average document size: Unknown; measure rendered message content during the bounded crawl without logging content.
- Freshness requirement: Not provided.
- Source API limits: No fixed quota found in reviewed endpoint docs; message pages should not exceed 1,000.
- Recommended crawl frequency: Daily full crawl initially, adjusted after measuring volume, duration, rate limits, and desired freshness.
- Deployment/hosting: A scheduled Python process or job with network access to Zulip and Glean; owner and platform remain to be selected.

Large organizations may make daily full replacement impractical. If the measured run cannot fit the schedule safely, pause rollout and design a developer-owned incremental connector.

## Open pre-production decisions

1. Provide and validate the exact `ZULIP_SITE`.
2. Select the hosting owner/platform.
3. Confirm desired freshness and acceptable crawl window.
4. Measure channel/message counts and average message size.
5. Decide whether archived channels should be indexed.
6. Validate private-user identity mapping and historical completeness with read-only credentials.
