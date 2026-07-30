# Webex API — Read-Only Probe Log

All calls used `Authorization: Bearer <REDACTED>` against base URL `https://webexapis.com/v1`.
Probes run via `connectors/webex/.glean/run_probes.sh` on 2026-07-21. Test org: `stevesmith-7xdw` (customer test tenant).
Token identity: org **full admin** (`id_full_admin` role). Personal access token (expires ~12h).

## 1. GET /people/me — auth smoke test
- Status: **200 OK**
- Confirms auth works; returns caller identity + `orgId`.
- Fields observed: `id`, `emails[]`, `displayName`, `firstName`, `lastName`, `nickName`, `orgId`, `roles[]`, `licenses[]`, `created`, `lastModified`, `lastActivity`, `status`, `type` (`person`), `siteUrls[]`, `avatarProvided`, `sipAddresses[]`.

## 2. GET /rooms?max=3&sortBy=lastactivity — list spaces
- Status: **200 OK**
- Pagination header present: `Link: <...&cursor=...>; rel="next"` (RFC5988 cursor).
- Item fields observed: `id`, `title`, `type` (`group`|`direct`), `lastActivity`, `teamId` (optional), `creatorId`, `created`, `ownerId`, `isPublic`, `isReadOnly`, `isLocked`.
- NOTE: returns only rooms the **authenticated user is a member of**, even for an admin token. Org-wide coverage needs compliance approach (see source_investigation.md).

## 3. GET /messages?roomId=<id>&max=3 — list messages in a room
- Status: **200 OK**
- Item fields observed (minimal message): `id`, `roomId`, `roomType`, `text`, `personId`, `personEmail`, `created`.
- Additional documented fields (appear when present): `markdown`, `html`, `files[]` (attachment URLs), `parentId` (threaded replies), `mentionedPeople[]`, `mentionedGroups[]`, `updated`, `isVoiceClip`.
- Requires `roomId` for group spaces. No server-side full-text; must page per room.

## 4. GET /memberships?roomId=<id>&max=3 — room membership (permissions)
- Status: **200 OK**
- Pagination header present: `Link ... rel="next"`.
- Item fields observed: `id`, `roomId`, `roomType`, `personId`, `personEmail`, `personDisplayName`, `personOrgId`, `isModerator`, `isMonitor`, `created`.
- This is the per-room ACL source for Glean document permissions.

## 5. GET /people?max=3 — list people
- Status: **200 OK**
- Pagination header present: `Link ... rel="next"`.
- Response wrapper also includes `notFoundIds` (used when querying by `id`).
- Item fields: same shape as /people/me.
- NOTE: unbounded `GET /people` (no filter) requires listing to be permitted; admin token returned org users. Can also fetch by `id` batch (`?id=a,b,c`) or by `email`.

## Cross-cutting confirmations
- Base URL: `https://webexapis.com/v1` (confirmed live via Link headers).
- Pagination: cursor via `Link: <url>; rel="next"` — confirmed live for rooms, memberships, people.
- Rate limiting (docs): `429 Too Many Requests` + `Retry-After: <seconds>` header.
- Auth: single `Authorization: Bearer` header; personal token OK for exploration, OAuth integration/bot token for production.

## 6. Compliance Events API probes (org-wide coverage) — 2026-07-21

Token has compliance scopes (all `/events` calls returned 200).

### GET /events?resource=messages&type=created&max=2
- Status: **200 OK**
- Pagination: `Link ... rel="next"` with `cursor`, `from`, `to`. Response auto-set `from` ≈ 1 month ago.
- Event shape: `id`, `resource`, `type`, `actorId`, `created`, `data{ id, roomId, roomType, text, personId, personEmail, created }`.
- **event.data contains the full message content** — org-wide content source without needing /messages.

### GET /events?resource=messages&from=2025-07-01...&to=2026-07-21 (1yr) and 2023-01-01 (3yr)
- Status: **403 Forbidden** — `error = 'User is only authorized to search within past 90 days.'`
- ⇒ **Hard 90-day lookback limit** on compliance events. Defines the coverage window.

### GET /events?resource=messages&type=deleted&max=2
- Status: **200 OK**. Deletion events exist.
- data shape: `{ id, roomId, roomType, personId, personEmail }` (no text). ⇒ deletion signal available (message id + roomId).

### GET /events?resource=messages&type=updated
- Status: **200 OK**, but **no updated events** in test org (edits rare). Documented behavior: updated event.data carries new text.

### GET /events?resource=rooms&max=2
- Status: **200 OK**. Room create/update events exist (`type=updated` observed).

### Cross-room capability test (rooms in events but NOT in caller's /rooms)
- Found **7** event-discovered rooms the admin is not a member of.
- `GET /messages?roomId=<not-mine>` → **HTTP 404** (message listing is membership-scoped; NOT org-wide even for compliance).
- `GET /memberships?roomId=<not-mine>` → **HTTP 200**, returned members (ACL IS readable org-wide).
- ⇒ Org-wide **content** = Events API only; org-wide **ACL** = /memberships per room.

