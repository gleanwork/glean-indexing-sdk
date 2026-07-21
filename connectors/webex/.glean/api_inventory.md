# Webex API Inventory (Messaging)

Base URL: `https://webexapis.com/v1`
Auth: `Authorization: Bearer <token>` (personal token for exploration; OAuth integration / bot token for production).
All endpoints below verified live against test org `stevesmith-7xdw` on 2026-07-21 unless noted.

## Objects → Endpoints (org-wide compliance model)

| Glean concept | Webex object | Endpoint | Verified |
|---|---|---|---|
| Document (org-wide) | Message events | `GET /events?resource=messages` | ✅ |
| Permissions (ACL, org-wide) | Room membership | `GET /memberships?roomId=` (cross-room ✅) | ✅ |
| Identity | Person | `GET /people`, `GET /people/me` | ✅ |
| Container metadata | Room | `GET /rooms` (account-scoped; metadata only) | ✅ |

> Membership-scoped `GET /messages?roomId=` and `GET /rooms` do **not** provide org-wide content (cross-room `/messages` → 404). They are retained only as metadata/fallback. Org-wide content = Events API.

### GET /events — compliance events (PRIMARY org-wide content)
- Query: `resource=messages|memberships|rooms`, `type=created|updated|deleted`, `from`/`to` (ISO), `max`.
- Pagination: cursor via `Link` rel="next" (carries `cursor`, `from`, `to`).
- **HARD LIMIT: 90-day lookback** — `from` older than 90 days → `403 "only authorized to search within past 90 days"` (verified).
- Message event shape: `id`, `resource`, `type`, `actorId`, `created`, `data{ id, roomId, roomType, text, personId, personEmail, created }`.
- Deleted event data: `{ id, roomId, roomType, personId, personEmail }` (no text) → deletion signal.
- Scope: `spark-compliance:events_read` + Compliance Officer role.


## Endpoint details

### GET /rooms — list spaces
- Query: `max` (page size), `sortBy=lastactivity|created|id`, `type=group|direct`, `teamId`.
- Pagination: `Link: <...cursor=...>; rel="next"` (RFC5988). Confirmed live.
- Fields: `id`, `title`, `type` (`group`/`direct`), `created`, `lastActivity`, `creatorId`, `ownerId`, `teamId?`, `isPublic`, `isReadOnly`, `isLocked`.
- **Scope limit:** returns only rooms the caller is a member of (even with admin token). Org-wide coverage requires the compliance/Events approach — see source_investigation.md.

### GET /messages — list messages in a room
- Query: `roomId` (**required**), `max`, `before` (ISO time), `beforeMessage` (message id), `parentId` (thread), `mentionedPeople`.
- Pagination: cursor via `Link` rel="next".
- Fields: `id`, `roomId`, `roomType`, `text`, `markdown?`, `html?`, `files?[]`, `personId`, `personEmail`, `created`, `updated?`, `parentId?` (threaded reply), `mentionedPeople?[]`, `isVoiceClip?`.
- Content strategy: iterate all rooms → page messages per room. `text` is the searchable body; `parentId` groups thread replies.

### GET /memberships — room ACL
- Query: `roomId`, `personId`, `personEmail`, `max`.
- Pagination: cursor via `Link` rel="next".
- Fields: `id`, `roomId`, `roomType`, `personId`, `personEmail`, `personDisplayName`, `personOrgId`, `isModerator`, `isMonitor`, `created`.
- Use: build per-room allow-list of people for Glean document permissions.

### GET /people — identities
- Query: `id` (batch, comma-sep), `email`, `displayName`, `orgId`, `max`.
- Pagination: cursor via `Link` rel="next". Response wrapper: `{ items[], notFoundIds }`.
- Fields: `id`, `emails[]`, `displayName`, `firstName`, `lastName`, `nickName`, `orgId`, `status` (`active`/…), `type` (`person`/`bot`/`appuser`), `lastActivity`, `created`.

## Pagination
RFC5988 Web Linking. Each list response may include `Link: <next-url>; rel="next"`. Follow `next` until absent. Page size via `max`.

## Rate limiting
`429 Too Many Requests` with `Retry-After: <seconds>`. Policy is fine-grained/undocumented in exact numbers; connector must honor `Retry-After` and back off.

## Deletion / incremental signals
- Compliance Events API exposes `type=created|updated|deleted` per resource → deletion + edit signals ARE available (within 90 days).
- **Coverage window: 90 days** (hard API limit). Older content not retrievable org-wide.
- V1 = **full crawl** over the 90-day window each run: reconcile created/updated (latest text) minus deleted, upload as full crawl, Glean stale-document deletion prunes docs that aged out or were deleted.
- Incremental (checkpoint `from`=last-run, page only new events) is a natural follow-up but developer-owned, NOT in V1.
