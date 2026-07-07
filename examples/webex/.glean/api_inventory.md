# Webex API Inventory

Source of truth: [Webex REST API](https://developer.webex.com/docs/api/getting-started). Base URL `https://webexapis.com/v1`.
All endpoints below were **verified live** against a real Webex org (admin token) on 2026-07-06.

## Conventions
- **Auth:** `Authorization: Bearer <token>`.
- **Pagination:** Cursor-based. Responses include an RFC5988 `Link:` header with `rel="next"` when more pages exist; follow until absent. `max` sets page size.
- **Rate limits:** `429` with `Retry-After` when throttled; connector must honor it.
- **Tracing:** every response carries a `trackingid` header; log it on errors.

## Endpoints in scope (v1)
| Endpoint | Method | Purpose | Verified |
|---|---|---|---|
| `/people/me` | GET | Auth check; identify token owner + org | yes |
| `/rooms` | GET | List spaces/rooms (documents + message containers) | yes |
| `/messages?roomId=` | GET | List messages in a room (documents) | yes |
| `/memberships?roomId=` | GET | Room members -> per-space permissions (allowed_users by email) | yes |

## Verified response shapes
- **Room:** `id, title, type (group|direct), lastActivity, teamId, creatorId, created, ownerId, isPublic, isReadOnly, isLocked`
- **Message:** `id, roomId, roomType, text, personId, personEmail, created` + optional `html, files (list), mentionedPeople (list), parentId`
- **Membership:** `id, roomId, roomType, personId, personEmail, personDisplayName, personOrgId, isModerator, isMonitor, created`

## Notes / confidence gaps
- Only `group` and `direct` rooms observed. Default v1 = group spaces only (DMs are private 1:1).
- Incremental via `/messages` `before`/`beforeMessage`; deferred to follow-up.
- `files` are auth-protected URLs; v1 records presence, does not fetch binaries.
