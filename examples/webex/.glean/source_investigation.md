# Webex Source Investigation

Datasource: **Webex** · Base URL: `https://webexapis.com/v1` · Investigated 2026-07-16 (live probes + official docs).
**Access model: org-wide via Compliance Officer + Events API, rolling ~90-day window (user-confirmed).**

## Authentication
- **Mechanism:** Bearer token (`Authorization: Bearer <token>`).
- Test auth: the token in `.glean/.env` — confirmed to hold **Compliance Officer** access (org-wide). Verified via `/people/me` (200) and `/events` (200).
- Production auth: a **Compliance Officer** identity (assigned in Control Hub) with a Service App / OAuth integration holding `spark-compliance:events_read`, `spark-compliance:messages_read`, `spark-compliance:rooms_read`, `spark-compliance:memberships_read` (+ `spark:people_read`). Long-lived, refreshable. A plain user/bot token only sees its own spaces and CANNOT do org-wide crawl.

## Source data model
- **Event:** org-wide activity record. `resource=messages` events carry the message in `event.data`; `type` is `created`/`updated`/`deleted`.
- **Message:** belongs to one room (`roomId`); `text` always, `html`/`files`/`parentId`/`updated` conditional.
- **Room (space):** `group` or `direct`; `title`, `description`, timestamps, `creatorId`/`ownerId`, optional `teamId`.
- **Membership:** person↔room join; carries identity (`personId`, `personEmail`, `personDisplayName`, `personOrgId`) and `isModerator`.

## Sync model
- **v1 = rolling ~90-day full crawl.** Each run walks the Events feed from ~89 days ago to now, groups messages by room, and pushes with full-crawl stale-deletion ON → Glean holds a rolling org-wide 90-day window.
- **Hard platform cap:** `/events` `from` cannot exceed ~90 days back (probed: −90d = 200, −120d = 403). Older messages are NOT retrievable via Events (would need Webex eDiscovery/archive export — out of scope).
- **Deletions:** `type=deleted` events give removed message ids (skipped during the crawl); anything absent from the crawl is pruned by full-crawl deletion.
- **Edits:** `type=updated` event `data` supersedes the `created` data for the same message id (keeps indexed text current within the window).
- **Incremental accumulation (follow-up, not built):** persist a cursor/last-run timestamp, run `INCREMENTAL` with `disable_stale_deletion_check`, and apply created/updated/deleted deltas so Glean retains history beyond 90 days. Deliberately out of v1 per the guided full-crawl-only scope.

## Permissions / ACL model
- Access to a Webex space is governed by **membership**. Allowed-viewer set for a room = `/memberships?roomId=` person emails.
- Glean strategy (email-based per-document ACLs): each Space and Message doc sets `permissions.allowed_users = [UserReferenceDefinition(email=...)]` for the room's members; config `is_user_referenced_by_email=True`.
- Streaming `index_data` runs content-only (no identity graph push); ACLs enforced purely by email references. Pushing a datasource identity/group graph is a follow-up.
- Direct rooms → the two participants. Guests (different `personOrgId`) are included as viewers (resolve only if known to Glean).

## Load / scale considerations
- Volume ≈ 90-day org-wide message count. The crawl materializes message events in memory (grouped by room) before emitting — bounded but not truly streaming on fetch; noted as a scale follow-up (Events can't be filtered per-room, so org-wide collect-then-group is required).
- Per unique room: 1 `GET /rooms/{id}` + paged `/memberships`. Cache room+membership lookups.
- Rate limiting: `429` + `Retry-After`; backoff. Keep `max=100`.
- Recommended crawl frequency: **daily** full crawl (rolling window + moderate freshness).

## Unknowns / confidence gaps
1. **Exact lookback cap:** probed between 90d (ok) and 120d (403); treating **89 days** as the safe default `from`. Configurable via `WEBEX_EVENTS_LOOKBACK_DAYS`.
2. **Rate-limit specifics:** no `x-ratelimit-*` headers observed; rely on `429`/`Retry-After` backoff.
3. **Attachment content:** `files` are auth-protected URLs; v1 indexes message text + a file reference, not file bytes (follow-up).
4. **Threading:** `parentId` links replies; v1 indexes replies as standalone message docs.
5. **Rooms with only >90-day-old messages** won't appear in the Events window, so they won't be indexed in v1 (acceptable given rolling-window model).
