# Connector Plan: Webex Messaging

## Goal

Build a Webex Messaging connector that indexes people, teams, rooms, memberships, and message threads into Glean using the Glean Indexing SDK. The first version is a local PAT-backed prototype, so it should index the authenticated user's visible Webex content and make the limitation explicit.

## SDK Shape

- Connector base class: `BaseStreamingDatasourceConnector[WebexDocument]` for room and message-thread documents.
- Data client type: `StreamingConnectorDataClient[WebexDocument]` backed by `PullHttpClient`.
- Pull layer primitives: `PullHttpClient`, `BearerTokenAuth`, `PullOptions`, `RateLimitConfig`, and `LinkHeaderPaginator`.
- Push layer operations: document bulk uploads through the datasource connector. Identity indexing should use SDK push-layer APIs or a small companion identity sync once the implementation shape is selected.

## Source Data Model

| Source object | Glean target | Notes |
| --- | --- | --- |
| Person | Datasource user | Use Webex person ID as datasource user ID; retain email/display name. |
| Team | Datasource group | Group name should be stable and namespaced, such as `team:<teamId>`. |
| Team membership | Datasource membership | Person belongs to team group. |
| Room | Document and/or group | Index a room summary document; create `room:<roomId>` group for room ACLs. |
| Room membership | Datasource membership and ACL input | Person belongs to room group; use for room/message permissions. |
| Message thread | Document | Group root message plus replies into one searchable document when parent/root metadata is available. |

## Glean Datasource Config

- Datasource name: `webex`
- Display name: `Webex`
- Datasource category: `PUBLISHED_CONTENT`
- URL regex: `^https://(?:app\\.)?webex\\.com/.*`
- Object definitions: none for the first document datasource version.

## Identity And Permissions

- Users: index Webex people before documents where possible.
- Groups: index Webex teams and rooms as datasource groups.
- Memberships: index team memberships and room memberships.
- Document permissions: room documents and message-thread documents should use `allowedGroups=["room:<roomId>"]` or equivalent SDK model fields. The first PAT prototype may simplify to explicit allowed users if group push support is not wired in this repo path yet.

## Pull Implementation

- Auth: `BearerTokenAuth(os.environ["WEBEX_ACCESS_TOKEN"])`; production OAuth refresh is out of scope for the PAT prototype.
- Pagination: `LinkHeaderPaginator(items_key="items")` for every list endpoint.
- Rate limiting: `RateLimitConfig(calls=240, period_seconds=60, strategy="rolling")`.
- Retry: SDK defaults retry 429/500/502/503/504 and respect `Retry-After`; consider adding 423 if attachment downloads are introduced.
- Checkpoint: accept optional `since` from `get_source_data(since=None)`; later persist per-room checkpoints in the runner.

## Local Configuration

- `.env.example` fields: `WEBEX_ACCESS_TOKEN`, `GLEAN_SERVER_URL` or `GLEAN_INSTANCE`, `GLEAN_INDEXING_API_TOKEN`, optional `WEBEX_MAX_ROOMS`, optional `WEBEX_SINCE`.
- `.env` user-provided fields: same values with real secrets.
- Values required before first real run: valid Webex PAT, Glean indexing token, target Glean instance/server URL, and datasource name/config confirmation.

## Push Implementation

- Full crawl: fetch identities first, then rooms and messages; upload all current documents through bulk indexing so stale Glean docs can be removed at completion.
- Incremental crawl: fetch active rooms and new messages since checkpoint; upsert documents and refresh permissions for touched rooms.
- Deletes: rely on periodic full crawls for stale deletion until Webex delete/tombstone behavior is confirmed.
- Permission updates: refresh room memberships when a room is crawled; schedule periodic full permission refresh.

## Ongoing Crawl Plan

- First successful full crawl validation: verify datasource config, document count, sample room document, sample message-thread document, and access checks for one allowed and one disallowed user.
- Change signal available? Partial. Rooms expose activity timestamps and messages expose creation timestamps, but delete/edit guarantees need confirmation.
- Recommended ongoing mode: combine frequent incremental crawls with scheduled full crawls.
- Suggested cadence: incremental every 15-30 minutes for active rooms in a prototype; daily full crawl for stale deletion and permission repair.
- Scheduling owner/infrastructure: outside the SDK. The SDK connector should be runnable from cron, a container job, or the eventual connector runner.

## Tests

- Unit tests: mock Webex pages, Link headers, 429 `Retry-After`, empty-page-with-next, and message-thread grouping.
- Pull + push tests: use mocked `PullHttpClient` responses plus `mock_glean_client`/test harness to verify generated documents.
- Recording/replay tests: optional sanitized Webex JSON fixtures for people, rooms, memberships, messages.
- Manual validation: run with PAT on a small Webex workspace; verify private-room ACL behavior before indexing broad content.

## Open Questions

- Which exact Webex message fields should define thread root and replies in current API responses?
- Should first implementation index room summary documents, message-thread documents, or both by default?
- Is group/membership push support already exposed in the preferred SDK path, or should v1 use document-level `allowedUsers` while identity push is added?
- What production auth model will replace PAT if this becomes an org-wide connector?

## Connector MCP Steps

- `create_connector`: create `webex` connector package with streaming datasource shape.
- `set_config`: datasource name `webex`, display name `Webex`, category `PUBLISHED_CONTENT`, Webex URL regex.
- `update_schema` / `infer_schema`: define `WebexDocument` fields for id, type, title, url, room id/title, body, creator, created, updated, allowed users/groups.
- `confirm_mappings`: map room/message thread records to `DocumentDefinition`.
- `build_connector`: generate code only after these planning artifacts are accepted.
- `get_data_client` / `update_data_client`: implement `PullHttpClient` + `LinkHeaderPaginator` Webex client.
- `run_connector` / `inspect_execution`: wait until `.env` contains valid Webex and Glean tokens.
