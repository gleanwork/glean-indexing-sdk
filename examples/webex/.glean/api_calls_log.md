# Webex Read-Only Probe Log

All probes were `GET` requests. `Authorization: Bearer <REDACTED>` on every call. Run 2026-07-16.
IDs, emails, and cursors redacted. Base URL: `https://webexapis.com/v1`.

## Probe 1 — Auth check
- Request: `GET /people/me`
- Status: **200**
- Headers: `content-type: application/json`, `trackingid: <REDACTED>` (no rate-limit headers returned)
- Body shape (top-level keys): `avatarProvided, created, displayName, emails, extensionProvided, firstName, id, invitePending, lastActivity, lastModified, lastName, licenses, loginEnabled, nickName, orgId, phoneNumbersProvided, roles, sipAddresses, siteUrls, status, type`
- Result: auth valid; principal has `orgId`, single email, `type=person`.

## Probe 2 — List rooms
- Request: `GET /rooms?max=5`
- Status: **200**
- Pagination: `Link: <https://webexapis.com/v1/rooms?max=5&cursor=<REDACTED>>; rel="next"`
- Items: 5 (types observed: `direct`, `group`)
- Room object keys: `created, creatorId, id, isLocked, isPublic, isReadOnly, lastActivity, ownerId, teamId, title, type`

## Probe 3 — List memberships
- Request: `GET /memberships?roomId=<REDACTED>&max=5`
- Status: **200**
- Items: 3
- Membership object keys: `created, id, isModerator, isMonitor, personDisplayName, personEmail, personId, personOrgId, roomId, roomType`
- Confirms ACL data available: `personEmail`, `personId`, `personOrgId`, `isModerator`.

## Probe 4 — List messages
- Request: `GET /messages?roomId=<REDACTED>&max=3`
- Status: **200**
- Items: 1
- Message object keys: `created, id, personEmail, personId, roomId, roomType, text`
- Note: `html`, `markdown`, `files`, `parentId`, `updated` absent on this plain-text message (optional fields, present only when applicable per docs).

## Not probed (deliberately)
- Any write/POST/PUT/DELETE endpoint — read-only exploration only.
- `/people?id=` bulk lookups — deferred to implementation; membership responses already carry `personEmail`/`personDisplayName`.

---

## Compliance / org-wide probes (Events API) — run 2026-07-16

The token in `.glean/.env` was found to carry **Compliance Officer** access, enabling org-wide reads via `/events`.

## Probe 5 — Events access check
- Request: `GET /events?resource=messages&max=1`
- Status: **200**
- Event object keys: `actorId, created, data, id, resource, type`
- `event.data` (message) keys: `created, id, personEmail, personId, roomId, roomType, text`
- Result: token has `spark-compliance:events_read` (org-wide message feed).

## Probe 6a — Events pagination + window
- Request: `GET /events?resource=messages&max=5`
- Status: **200**; 5 events across 3 distinct roomIds
- `Link: <.../events?resource=messages&cursor=<REDACTED>&from=2026-06-21T...Z&max=5&to=2026-07-16T...Z>; rel="next"`
- Note: API auto-injects a `from`/`to` window (default ~ last 25 days) and cursor pagination.

## Probe 6b — Event types
- `GET /events?resource=messages&type=updated&max=1` -> **200**, 0 items (no recent edits)
- `GET /events?resource=messages&type=deleted&max=1` -> **200**, 1 item (deletions ARE exposed)

## Probe 6c — Historical lookback cap
- `GET /events?...&from=2020-01-01T00:00:00.000Z` -> **403** (too far back)
- Binary search of `from` (relative to 2026-07-16): -365d/-180d/-120d -> **403**; -90d/-60d/-45d/-35d -> **200**
- Conclusion: **max lookback ~ 90 days** (hard Webex platform cap on the Events feed).

## Probe 6d — Org-wide room + membership reads
- `GET /rooms/{roomId}` (roomId from an event) -> **200**; keys: `created, creatorId, description, id, isLocked, isPublic, isReadOnly, lastActivity, madePublic, ownerId, title, type`
- `GET /memberships?roomId={roomId}&max=3` -> **200**; 3 members
- Conclusion: compliance token can read ANY room's details + membership org-wide (needed for space docs + ACLs).
