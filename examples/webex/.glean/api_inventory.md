# Webex API Inventory

Datasource: **Webex** · Base URL: `https://webexapis.com/v1`
Source of truth: Webex REST API v1 (https://developer.webex.com/docs/api/v1), confirmed by user 2026-07-16.
**Access model: org-wide via Compliance Officer token + Events API (rolling ~90-day window).** All endpoints verified with live read-only probes (see `api_calls_log.md`).

## Auth

- Bearer token in `Authorization: Bearer <token>` header.
- The token in `.glean/.env` carries **Compliance Officer** access → org-wide reads via `/events`, `/rooms/{id}`, `/memberships`.
- Compliance scopes: `spark-compliance:events_read`, `spark-compliance:messages_read`, `spark-compliance:rooms_read`, `spark-compliance:memberships_read` (+ `spark:people_read` for `/people/me`).
- Auth verified via `GET /people/me` → 200 and `GET /events` → 200.

## Endpoints in scope (v1)

| Endpoint | Method | Path | Role |
|---|---|---|---|
| Get my details | GET | `/people/me` | Auth check + principal identity |
| **List events** | GET | `/events?resource=messages` | **Primary org-wide content feed** (created/updated/deleted) |
| Get room details | GET | `/rooms/{roomId}` | Space document details for discovered rooms |
| List memberships | GET | `/memberships?roomId=` | Per-room ACL (allowed_users by email) |
| List rooms | GET | `/rooms` | Supporting/diagnostic only (token-visible spaces) |

## Crawl shape (org-wide, rolling 90-day full crawl)

1. `GET /events?resource=messages&type=deleted&from=<~90d ago>` (paged) → set of deleted message ids to skip.
2. `GET /events?resource=messages&type=created&from=<~90d ago>` (paged) → message events. Merge `type=updated` events so edited messages carry latest `data`.
3. Group surviving messages by `roomId`.
4. Per unique room: `GET /rooms/{roomId}` (Space doc) + `GET /memberships?roomId=` (member emails for ACL).
5. Emit one Space record per room + its Message records.

## Behavior summary

- **Pagination:** cursor via `Link` header `rel="next"` on `/events` and `/memberships`. Page size `max` (use 100).
- **Time window:** `/events` requires `from`/`to`; **max lookback ≈ 90 days** (hard platform cap — `from` older than ~90 days → 403). If `from` omitted the API defaults to ~last 25 days, so we set `from` explicitly to ~89 days ago to maximize coverage safely under the cap.
- **Retention model (v1, confirmed):** rolling ~90-day window with **full-crawl semantics** — the SDK prunes docs not seen in the current crawl, so the Glean index holds a rolling org-wide 90-day window. Accumulating older history requires incremental mode + disabled stale-deletion (follow-up).
- **Deletions/edits:** `type=deleted` ids are skipped; `type=updated` data supersedes `type=created` data for the same message id. Anything older than the window is naturally pruned by full-crawl.
- **Rate limiting:** `429` + `Retry-After`; client backs off and retries.

## Field mapping notes

**Event → message:** `event.data` is the message object: `id`, `roomId`, `roomType`, `text`, `html`/`files`/`parentId`/`updated` (when present), `personId`, `personEmail`, `created`.

**Room (`/rooms/{id}`) → space document:** `id`, `title`, `type`, `description`, `created`, `lastActivity`, `creatorId`, `ownerId`, `teamId`.

**Membership → ACL:** the set of `personEmail` for a room = allowed-viewers for that room's space doc and all its message docs. `personOrgId` distinguishes guests (still included as viewers).
