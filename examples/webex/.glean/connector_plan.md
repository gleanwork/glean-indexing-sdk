# Webex Connector Plan

Status: confirmed
Last updated: 2026-07-06

## Product scope (v1)
Index Webex **group spaces** and the **messages** within them into a Glean custom datasource so employees can search Webex conversations from Glean.
- Entities indexed as documents: (1) Rooms/Spaces, (2) Messages in spaces.
- Crawl mode: full crawl only. Incremental is a documented follow-up.
- Room types: group only in v1. direct (1:1 DMs) excluded by default.

## Source endpoints and usage
| Endpoint | Usage |
|---|---|
| `GET /people/me` | Startup auth check; log token owner + org (redacted). |
| `GET /rooms` (type=group) | Enumerate spaces -> one Space document each + container for messages. Cursor-paginated. |
| `GET /messages?roomId=` | Page all messages per room -> one Message document each. Cursor-paginated. |
| `GET /memberships?roomId=` | Room members -> per-space allowed_users permissions (by email). Cursor-paginated. |

## SDK usage
- SDK usage: Full connector flow (fetch, transform, upload) using BaseStreamingDatasourceConnector + BaseStreamingDataClient.
- Rationale: Webex messages are paginated per-room and can be large in production; streaming yields incrementally instead of holding all in memory. (Verified exports exist; the README's `BaseConnectorDataClient` alias does NOT exist in this repo.)
- Data flows as a discriminated item: {kind: room|message, ...}; transform() maps each to a DocumentDefinition.

## Glean mapping
Datasource config (CustomDatasourceConfig):
- name="webex", display_name="Webex"
- datasource_category=MESSAGING
- is_user_referenced_by_email=True
- url_regex for https://web.webex.com/...

Space document: object_type="Space", id=room.id, title=room.title, created_at/updated_at from created/lastActivity, permissions = room members.

Message document: object_type="Message", id=message.id, title derived ("<author> in <room title>", truncated), body=ContentDefinition(text_content=text), author=UserReferenceDefinition(email=personEmail), created_at=created, container=parent room, permissions = room members.

## Permissions
- DocumentPermissionsDefinition(allowed_users=[email per room member]).
- Requires /memberships per room. If unreadable for a room, skip its docs (fail-closed). Decision point.

## Auth
- Test auth: read-only Webex bearer token, verified live.
- Production auth: WEBEX_API_TOKEN bearer env var placeholder; concrete model (bot / OAuth / compliance) decided later per user instruction.

## Observability
- Provider: SDK ConnectorObservability (built into the base connector).
- Lifecycle logs: connector start/end, per-room fetch start, page counts, transform count, upload batch results.
- Metrics: rooms scanned, messages fetched, documents transformed, documents uploaded, skipped (no-permission), API error/429 count.
- Evaluation/debug checks: log trackingid on API errors; redact tokens; assert non-zero docs when rooms exist.

## Scale / operations
- Test org: ~14 rooms, ~41 messages (tiny, good for eval).
- Expected prod: document count ~ total messages across visible spaces; avg doc size small (< 1 KB typical).
- Freshness: daily full crawl reasonable for v1.
- Source limits: honor Webex 429 + Retry-After; cursor Link pagination.
- Recommended crawl frequency: daily (full).

## Deployment / hosting
- Runnable as a script/cron job (env: GLEAN_SERVER_URL, GLEAN_INDEXING_API_TOKEN, WEBEX_API_TOKEN). Detailed hosting TBD; not blocking v1 code.

## Follow-up work (out of scope for v1)
- Incremental crawl via /messages before/checkpointing.
- Direct (DM) rooms.
- Attachment/file binary content indexing.
- Thread reconstruction via parentId.

## Open decisions for you to confirm
1. Group rooms only (exclude DMs)? (default: yes)
2. Permissions = room members via /memberships, fail-closed if unreadable? (default: yes)
3. Streaming connector (BaseStreamingDatasourceConnector)? (default: yes)
4. Datasource name webex / display Webex? (default: yes)
