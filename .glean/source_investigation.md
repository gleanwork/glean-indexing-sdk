# Source Investigation: Webex Messaging

## Confirmed Documentation

- Webex Messaging - Integrations and Authorization: https://developer.webex.com/messaging/docs/api/guides/integrations-and-authorization
- Webex Integrations - Scopes: https://developer.webex.com/docs/integrations#scopes
- Webex Basics - Pagination, Rate Limits, and API Errors: https://developer.webex.com/docs/basics#pagination
- Webex API Reference - Rooms: https://developer.webex.com/messaging/docs/api/v1/rooms
- Webex API Reference - Messages: https://developer.webex.com/docs/api/v1/messages
- Webex API Reference - Memberships: https://developer.webex.com/messaging/docs/api/v1/memberships
- Webex API Reference - Teams: https://developer.webex.com/messaging/docs/api/v1/teams
- Webex API Reference - Team Memberships: https://developer.webex.com/docs/api/v1/team-memberships
- Webex API Reference - People: https://developer.webex.com/docs/api/v1/people

## Source Objects

- Person: a registered Webex user; maps to a Glean datasource user.
- Team: a Webex team; maps to a datasource group.
- Team membership: a person-to-team relationship; maps to a datasource membership.
- Room: a collaboration space; maps to both a document and a room-scoped group.
- Room membership: a person-to-room relationship; maps to room/message ACLs and optionally room group memberships.
- Message: message content within a room; root messages plus replies should be grouped into one searchable thread document.

## Authentication

- Type: Bearer token for the first prototype, using a Webex personal access token.
- Required env vars: `WEBEX_ACCESS_TOKEN`.
- Required scopes: for PAT-backed local testing, use the token's available user-level scopes: `spark:people_read`, `spark:rooms_read`, `spark:memberships_read`, `spark:messages_read`, `spark:teams_read`.
- Token refresh: PAT is manual and suitable only for local prototyping. Production should move to OAuth refresh or a compliance/admin integration.
- Open questions: whether org-wide indexing is required. A user PAT only sees rooms/messages available to that user, so it cannot produce complete enterprise coverage.

## Endpoints

| Object | Method | Endpoint | Purpose |
| --- | --- | --- | --- |
| People | GET | `/people` | Fetch users for identity indexing. |
| Teams | GET | `/teams` | Fetch teams for group indexing. |
| Team memberships | GET | `/team/memberships?teamId=<teamId>` | Fetch team users for group memberships. |
| Rooms | GET | `/rooms` | Fetch rooms for room docs and room-scoped crawl fanout. |
| Room memberships | GET | `/memberships?roomId=<roomId>` | Fetch room ACLs and room group memberships. |
| Messages | GET | `/messages?roomId=<roomId>` | Fetch messages to build thread documents. |

## Pagination

- Strategy: RFC5988 `Link` response header with `rel="next"`.
- Page size: pass `max` where the endpoint supports it; if the requested max exceeds an endpoint-specific cap, Webex returns the endpoint maximum.
- Next page signal: continue until no `rel="next"` link remains.
- Edge cases: Webex notes that some APIs can return empty pages while a `next` link is still present. The connector should follow `next` until absent, not stop solely on an empty page.

## Rate Limits

- Limits: Webex says most REST APIs are around 300 requests per minute. `/people` and `/messages` have dynamically adjusted higher quotas.
- Retry guidance: 429 responses include `Retry-After`; attachment downloads can return 423 with `Retry-After` while malware scanning is pending.
- Backoff guidance: use SDK `PullHttpClient` retries with `respect_retry_after=true`; start with a conservative rolling limiter such as 240 calls per 60 seconds.

## Incremental Strategy

- High-water mark: use room `lastActivity` to find active rooms; use message `created` timestamp for message windows where supported by implementation filtering.
- Checkpoint storage: first version can accept a caller-provided `since` value. A production runner should persist per-room message high-water marks.
- Full crawl behavior: crawl people, teams, team memberships, rooms, room memberships, and all visible room messages; use bulk document upload semantics so stale docs can be deleted.
- Incremental crawl behavior: crawl rooms active since the checkpoint, refresh memberships for those rooms, and index new/updated message-thread documents.

## Permissions

- Identity objects: Webex people become Glean datasource users, preferably keyed by Webex person ID with email retained for display/reference.
- Group objects: Webex teams and private rooms can become datasource groups.
- Document ACL source: room memberships determine visibility for room documents and message-thread documents.
- Anonymous/public content: public rooms may be broader than room members, but the PAT view may not prove org-wide visibility. Treat all room/message documents as membership-restricted in the first version unless a production admin/compliance auth model validates public-room semantics.

## Deletes And Staleness

- Source delete signal: direct delete discovery is limited in a PAT crawl. Missing documents are best reconciled by scheduled full crawls.
- Glean delete behavior: full crawls can remove stale documents through bulk upload completion. Incremental crawls should only upsert and avoid deleting unseen documents.
- Full crawl repair strategy: run a periodic full crawl to repair stale memberships, room deletions, and deleted/edited message threads.

## Attachments And Binary Content

- Attachments supported: messages can include file attachments.
- Fetch endpoint: message `files` URLs can be fetched separately with auth.
- Size limits: Webex message attachments are limited to 100 MB each. Glean indexing should use conservative download caps and avoid indexing very large binaries in the first version.
- Parsing expectations: first version should index text/markdown/html message bodies and include attachment metadata or links, not binary payloads.

## Risks And Unknowns

- PAT scope is inherently partial and should not be presented as an org-wide connector.
- Production org-wide message indexing likely needs compliance scopes such as `spark-compliance:messages_read`, `spark-compliance:rooms_read`, `spark-compliance:memberships_read`, and related team scopes, or admin/compliance setup.
- Message edits and deletes need more investigation; if list endpoints do not expose reliable tombstones, scheduled full crawl is the deletion safety net.
- Thread grouping depends on Webex message fields for parent/root relationships; implementation should confirm exact response fields from sample API payloads.
