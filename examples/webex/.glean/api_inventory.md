# Webex API Inventory

Source of truth: [Webex REST API](https://developer.webex.com/docs/api/getting-started). Base URL `https://webexapis.com/v1`.
All endpoints below were **verified live** against a real Webex org on 2026-07-06.

## Conventions
- **Auth:** `Authorization: Bearer <token>`.
- **Pagination:** Cursor-based via RFC5988 `Link: rel="next"`; follow until absent. `max` sets page size.
- **Rate limits:** `429` with `Retry-After`; connector honors it (with retry/backoff).
- **Tracing:** every response carries a `trackingid` header; logged on errors.

## Endpoints in scope (v1)
| Endpoint | Method | Purpose | Verified |
|---|---|---|---|
| `/people/me` | GET | Auth check; identify token owner + org | yes |
| `/events?resource=messages` | GET | **Org-wide** message stream (Compliance Officer); embeds full message in `data` | yes |
| `/rooms/{id}` | GET | Resolve title/metadata for a room discovered from events | yes |
| `/memberships?roomId=` | GET | Room members -> permissions (works for arbitrary org rooms) | yes |
| `/rooms` | GET | Room-scoped client only: enumerate the token owner's rooms | yes |
| `/messages?roomId=` | GET | Room-scoped client only: messages within a room | yes |

## Verified response shapes
- **Room:** `id, title, type (group|direct), lastActivity, teamId, creatorId, created, ownerId, isPublic, isReadOnly, isLocked`
- **Message:** `id, roomId, roomType, text, personId, personEmail, created` + optional `html, files, mentionedPeople, parentId, updated`
- **Event:** `id, resource, type (created|updated|deleted), actorId, created, data` where `data` (for resource=messages) is the full message
- **Membership:** `id, roomId, roomType, personId, personEmail, personDisplayName, personOrgId, isModerator, isMonitor, created`

## OAuth scopes
- **Org-wide (Compliance Officer):** `spark-compliance:events_read`, `spark-compliance:messages_read`, `spark-compliance:memberships_read`, `spark-compliance:rooms_read`
- **Room-scoped (bot/user):** `spark:people_read`, `spark:rooms_read`, `spark:messages_read`, `spark:memberships_read`
- Confirm exact scope strings on the developer portal; org-wide behavior verified live, scope strings from documented conventions.

## Constraints verified live
- **Events API lookback ~90 days**: `from=2026-04-08` -> 200, `from=2026-04-01` -> 403. Client clamps over-old `start_date` forward with a warning; older history needs Webex eDiscovery.
- Org-wide events surface rooms the token owner is not a member of (14 org-wide vs 11 room-scoped in the test org).
- `direct` (DM) rooms excluded by default; `files` are auth-protected URLs (binaries not fetched in v1).
