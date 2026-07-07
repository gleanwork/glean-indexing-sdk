# Webex Connector Plan

Status: confirmed
Last updated: 2026-07-06

## Product scope (v1)
Index Webex **group spaces** and the **messages** within them into a Glean custom datasource so employees can search Webex conversations from Glean. **Org-wide** coverage is the chosen deployment model.
- Entities indexed as documents: (1) Rooms/Spaces, (2) Messages in spaces.
- Crawl mode: full crawl only. Incremental is a documented follow-up.
- Room types: group only in v1. direct (1:1 DMs) excluded by default.

## Source endpoints and usage
| Endpoint | Usage |
|---|---|
| `GET /people/me` | Startup auth check; log token owner + org (redacted). |
| `GET /events?resource=messages` | **Org-wide** message stream (Compliance Officer). Embeds full message in `data`. ~90-day lookback. Cursor-paginated. |
| `GET /rooms/{id}` | Resolve title/metadata for a room discovered from events. |
| `GET /memberships?roomId=` | Room members -> per-space allowed_users permissions (by email). Cursor-paginated. |
| `GET /rooms` | (Room-scoped alternative client only) enumerate the token owner's rooms. |

## SDK usage
- SDK usage: Full connector flow (fetch, transform, upload) using BaseStreamingDatasourceConnector + BaseStreamingDataClient.
- Two interchangeable data clients feed the same WebexConnector: WebexEventsDataClient (org-wide, Events API) and WebexDataClient (room-scoped, bot/user token).
- Org-wide client iterates the events stream, discovers rooms lazily, caches each room's title + current members once, emits a Space document per room then its messages.

## Glean mapping
Datasource config (CustomDatasourceConfig): name="webex", display_name="Webex", datasource_category=MESSAGING, is_user_referenced_by_email=True, url_regex for https://web.webex.com/...

Space document: object_type="Space", id="room:<id>", title=room.title, created_at/updated_at, permissions = room members.
Message document: object_type="Message", id="message:<id>", title derived, body=text, author=personEmail, created_at, container=room title, permissions = room members.

## Permissions
- DocumentPermissionsDefinition(allowed_users=[email per room member]) via /memberships (works for arbitrary org rooms with the compliance token).
- Fail-closed: if a room's membership/metadata can't be read, the room and its messages are skipped.

## Auth
- Test auth: read-only Webex bearer token (Compliance-Officer-capable), verified live; org-wide events + arbitrary-room memberships confirmed 200.
- Production auth: org-wide via a Compliance Officer token. Scopes: spark-compliance:events_read, spark-compliance:messages_read, spark-compliance:memberships_read, spark-compliance:rooms_read. (Room-scoped alternative: spark:people_read, spark:rooms_read, spark:messages_read, spark:memberships_read.) Confirm exact scope strings on developer.webex.com.

## Constraints verified live
- Events API lookback is capped at ~90 days: `from` older than ~90d returns 403. The client clamps an over-old start_date forward with a warning; older history requires Webex eDiscovery (out of scope).
- Org-wide events surface rooms the token owner is not a member of (14 rooms org-wide vs 11 room-scoped in the test org).

## Observability
- Provider: SDK ConnectorObservability (built into the base connector).
- Lifecycle logs: crawl start (with effective from-window), room discovery, per-room member counts, fetch-complete tallies (rooms indexed/skipped, messages).
- Metrics: rooms indexed, rooms skipped (fail-closed), messages, API error/429 count.
- Evaluation/debug checks: log trackingid on API errors; redact tokens; warn on clamp; assert non-zero docs when events exist.

## Scale / operations
- Test org (org-wide, ~90d): 14 spaces, 26 messages, 40 documents.
- Freshness: daily full crawl within the 90-day window.
- Source limits: honor Webex 429 + Retry-After; cursor Link pagination; 90-day events lookback.
- Recommended crawl frequency: daily (full).

## Deployment / hosting
- Runnable as a script/cron job: `uv run python -m examples.webex.main --org-wide [--start-date <iso>]` with GLEAN_SERVER_URL, GLEAN_INDEXING_API_TOKEN, WEBEX_API_TOKEN.

## Follow-up work (out of scope for v1)
- Incremental crawl (checkpoint the events window) and message edit/delete handling.
- History older than ~90 days (Webex eDiscovery).
- Direct (DM) rooms; attachment/file binary content; thread reconstruction via parentId.
