# Webex Connector Plan

**Status: confirmed** (user-approved 2026-07-16: per-message docs, include direct rooms, streaming base class, **org-wide via compliance Events API**, **rolling ~90-day window**)
Datasource: `webex` · SDK: glean-indexing-sdk · Author date: 2026-07-16

## 1. Goal & scope (v1)

A push connector that indexes **Webex spaces** and **messages** **org-wide** into a Glean custom datasource, with **per-document ACLs** derived from Webex room membership. Content is discovered through the **compliance Events API** (`/events`). Full connector flow: `get_data() → transform() → index_data()`, runnable end-to-end against the `salessavvy-test-be` Glean test datasource.

**In scope (v1):**
- Org-wide messages within the Events API window (~last 90 days) → one "Message" document each.
- The spaces (`group` + `direct` rooms) those messages belong to → one "Space" document each.
- Membership-based ACLs (each doc visible only to that room's members).
- Edits (`type=updated`) and deletions (`type=deleted`) applied within the window.

**Out of scope (follow-up):**
- Messages older than the ~90-day Events window (would need Webex eDiscovery/archive export).
- Incremental accumulation beyond the rolling window (persisted cursor + disabled stale-deletion — see §4).
- Attachment/file content extraction (index a file reference only).
- Teams and People as standalone documents.

## 2. Source endpoints (all verified via live probe — see api_inventory.md)

| Endpoint | Use in connector |
|---|---|
| `GET /people/me` | Startup auth check; log principal + orgId. |
| `GET /events?resource=messages` (paginated) | **Primary org-wide feed** — created/updated/deleted message events. |
| `GET /rooms/{roomId}` | Fetch discovered room details → Space docs. |
| `GET /memberships?roomId=` (paginated) | Per-room member set → ACL (`allowed_users` by email). |
| `GET /rooms` (paginated) | Supporting/diagnostic only (token-visible spaces); not used for org-wide discovery. |

Pagination: `Link` header `rel="next"` cursor on `/events` and `/memberships`. Rate limits: handle `429` + `Retry-After` with backoff. Page size `max=100`. Events `from` capped at ~90 days back (hard platform limit).

## 3. Entity → Glean document mapping

**Space document**
- `id`: `space:{roomId}`
- `object_type`: `Space`
- `title`: room `title`
- `container`: `team:{teamId}` when present (else none)
- `view_url`: `https://web.webex.com/spaces/{roomId}`
- `created_at`: from `created`; `updated_at`: from `lastActivity`
- `permissions.allowed_users`: room member emails

**Message document** (from `event.data`)
- `id`: `message:{messageId}`
- `object_type`: `Message`
- `container`: `space:{roomId}` (nests message under its space)
- `title`: `"{personDisplayName} in {roomTitle}"` (fallback to first ~80 chars of text)
- `body`: `ContentDefinition(mime_type=text/html or text/plain, text_content=html or text)`
- `author`: `UserReferenceDefinition(email=personEmail)`
- `view_url`: `https://web.webex.com/spaces/{roomId}` (Webex exposes no per-message web URL — space link is the best target; flagged as minor uncertainty)
- `created_at`: from `created`; `updated_at`: from `updated` when present
- `permissions.allowed_users`: room member emails
- Messages with a matching `type=deleted` event are skipped; `type=updated` data supersedes `type=created` data.

**Identities / ACL enforcement:** v1 uses **email-based per-document ACLs** — each doc's `permissions.allowed_users = [UserReferenceDefinition(email=...)]` for the room's members, with config `is_user_referenced_by_email=True` so emails resolve against Glean's known users. The streaming `index_data` runs a **content crawl only** (it does not call `get_identities()`), so no separate datasource identity graph is pushed in v1. This correctly permissions every document by room membership. Pushing a standalone datasource identity/group graph (e.g. for guests Glean doesn't already know) is a documented follow-up.

**ACL note:** direct rooms → the two participants; group rooms → full member list. Guests (different `personOrgId`) are included as viewers (resolve only if known to Glean).

## 4. Crawl behavior

- **Rolling ~90-day full crawl (confirmed).** Each run walks `/events?resource=messages` from ~89 days ago to now, groups messages by room, and pushes with full-crawl stale-deletion ON. The Glean index therefore holds a rolling org-wide 90-day window; docs not seen in the current crawl (older than the window, or deleted) are pruned by the `is_last_page` stale-deletion boundary.
- **Within-window edits/deletes:** `type=updated` data supersedes `type=created`; `type=deleted` message ids are skipped. No per-item delete calls needed — full-crawl pruning handles removals.
- **Hard platform cap:** `/events` `from` cannot exceed ~90 days (probed: −90d = 200, −120d = 403). Default `from` = 89 days ago (`WEBEX_EVENTS_LOOKBACK_DAYS`, configurable).
- **Incremental accumulation (follow-up, not built):** persist a cursor/last-run time, run `INCREMENTAL` with `disable_stale_deletion_check`, apply created/updated/deleted deltas so Glean retains history beyond 90 days.

## 5. Auth

- Test auth: the token in `.glean/.env` (`WEBEX_ACCESS_TOKEN`) — confirmed to hold **Compliance Officer** access; verified via `GET /people/me` (200) and `GET /events` (200).
- Production auth: a **Compliance Officer** identity (Control Hub) via Service App / OAuth integration with `spark-compliance:events_read`, `spark-compliance:messages_read`, `spark-compliance:rooms_read`, `spark-compliance:memberships_read` (+ `spark:people_read`) — long-lived, refreshable. A plain user/bot token only sees its own spaces and cannot crawl org-wide.

## 6. SDK usage

- SDK mode: full connector flow using `BaseStreamingDatasourceConnector` (streaming `get_data()` generator → `transform()` → streaming `index_data()`), driving Glean push via `bulk_index_single_batch_upload`.
- Base class: **`BaseStreamingDatasourceConnector[WebexRecord]`** (confirmed). Memory-efficient, batches uploads via `bulk_index_single_batch_upload` with a shared `upload_id`; natural fit for paginated Webex APIs. Note: its `index_data` is **content-only** (no identity crawl) — ACLs are email-based per §3.
- Data client: `WebexDataClient(BaseStreamingDataClient[WebexRecord])` — `get_source_data()` is a generator that: (1) pages `/events?resource=messages&type=deleted&from=~89d` → deleted id set; (2) pages `type=created` (+ merges `type=updated`) → message events, grouped by `roomId`, minus deleted ids; (3) per unique room, `GET /rooms/{roomId}` + paged `/memberships?roomId=` (cached) for details + member emails; (4) yields one `space` record per room followed by its `message` records. Tagged records: `{"kind": "space"|"message", "member_emails": [...], ...}`.
- Config: `CustomDatasourceConfig(name="webex", display_name="Webex", datasource_category=..., is_user_referenced_by_email=True, object_definitions=[Space, Message], is_test_datasource=True for the test run)`.
- `transform()` maps a batch of tagged records → `DocumentDefinition`s (space vs message branch).

## 7. Glean push / status endpoints (from connector-push skill)

- `PushUploader.configure_datasource()` → `datasources.add` (run once from `main.py` before crawl).
- `PushUploader.bulk_index_single_batch_upload()` → `/bulkindexdocuments` per batch (driven by the streaming base with a shared `upload_id`; first batch `is_first_page`, final batch `is_last_page` triggers the stale-document deletion boundary).
- Status/debug: `datasources.status` / document-in-datasource debug check post-run.

## 8. Observability (from connector-observability skill)

- Provider: built-in `ConnectorObservability` (already wired into `index_data`).
- Lifecycle logs: start/end execution, identity crawl, content crawl, upload batches (emitted by base + uploader).
- Metrics: base emits `items_fetched`, `documents_transformed`, `documents_indexed`, `indexing_errors`. Add custom (via data client / observability): `rooms_fetched`, `messages_fetched`, `memberships_fetched`, `webex_api_429_retries`.
- Evaluation checks: auth probe passes; counts are non-zero and internally consistent (docs = spaces + messages); a sampled doc appears in the datasource with expected ACL; **no secrets in logs** (bearer redacted).

## 9. Load / sizing

- Expected doc count: ~90-day org-wide message volume + the distinct rooms they belong to (test org is small — probes saw 3 distinct rooms in a 5-event page, 1–3 members/room).
- Avg doc size: messages are small (text); spaces tiny.
- Source limits: `/events` `from` capped at ~90 days; per-endpoint rate limits, `429`+`Retry-After`.
- Memory: the crawl materializes message events (grouped by room) before emitting — bounded by the 90-day window; noted as a scale follow-up (Events can't be filtered per-room).
- Recommended crawl frequency: **daily** full crawl (rolling window + moderate freshness need).

## 10. Deployment / hosting

- **In scope.** Customer-hosted via the SDK's `glean-deploy` CLI → GKE CronJob on GCP.
- **Target:** GCP project `dev-sandbox-334901`, Glean instance **glean-dev** (`https://glean-dev-be.glean.com`).
- **Cluster / namespace / region:** cluster `glean-deploy`, namespace `default`, region/zone `us-central1-a` (zonal cluster → Terraform `location = us-central1-a`).
- **Image:** `us-central1-docker.pkg.dev/dev-sandbox-334901/glean-connectors/webex` (Artifact Registry repo `glean-connectors`, us-central1).
- **Connector module/class:** `connector` / `WebexConnector`. `WebexConnector()` self-wires its data client from env and configures the datasource on run (run.py only calls `index_data`).
- **Cron:** `17 */6 * * *` (every 6 hours, off-minute), `concurrency_policy=Forbid`. Chosen for fresher indexing than daily while keeping load modest; consistent with rolling-window full-crawl (each run refreshes the last ~90 days).
- **Resources:** 500m CPU / 1Gi memory (headroom for in-memory event grouping).
- **SDK packaging:** SDK 1.0.0b2 isn't on PyPI, so the locally-built wheel is vendored into the image and installed via the connector's `pyproject.toml`.
- **Secrets:** uploaded to GCP Secret Manager under `CUSTOM_DATASOURCE_PLATFORM_WEBEX_` (`GLEAN_SERVER_URL`, `GLEAN_INDEXING_API_TOKEN`, `WEBEX_ACCESS_TOKEN`, `WEBEX_BASE_URL`, `WEBEX_EVENTS_LOOKBACK_DAYS`, `WEBEX_TEST_DATASOURCE`). Deployment-control vars (`DATASOURCE_NAME`, `CLOUD_PLATFORM`, `INDEXING_MODE`, `GOOGLE_CLOUD_PROJECT`) set by Terraform, not uploaded.
- **Deploy commands:** `glean-deploy build --push` → `glean-deploy secrets upload` → `glean-deploy apply`; operate with `glean-deploy status` / `logs`.
- Local dev run (no container): `cd examples/webex && uv run python main.py`.

## 11. Resolved decisions

1. **Message granularity:** per-message documents. ✓ confirmed
2. **view_url for messages:** space web URL `https://web.webex.com/spaces/{roomId}` (no per-message URL exists). ✓ accepted
3. **Direct (1:1) rooms:** included (ACL = the two participants). ✓ confirmed
4. **Base class:** `BaseStreamingDatasourceConnector`. ✓ confirmed
5. **Coverage:** org-wide via compliance Events API (token confirmed to hold Compliance Officer access). ✓ confirmed
6. **Retention:** rolling ~90-day window with full-crawl semantics (platform-capped). ✓ confirmed
