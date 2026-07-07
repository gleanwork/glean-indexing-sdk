# Webex Source Investigation

## Auth
- Test auth: read-only Webex bearer token, verified live on 2026-07-06.
- Production auth: WEBEX_API_TOKEN bearer env var placeholder; concrete model (bot / OAuth integration / compliance officer) to be decided later per user instruction.

## Source data model
- **Room (space):** group (multi-person) or direct (1:1 DM). Has title, timestamps, creator/owner, team linkage.
- **Message:** belongs to one room; plain `text` + optional `html`, `files`, `mentionedPeople`, `parentId`. Authored by a person (`personEmail`).
- **Membership:** person-to-room link with `personEmail`; basis for permissions.

## Sync model
- v1: full crawl only. Enumerate rooms, then page all messages per room, emit documents.
- Incremental (follow-up): `/messages` before/beforeMessage; checkpoint per-room latest created. Deferred.

## Permissions model
- Webex spaces are private to members. Correct Glean permissions = allowed_users = room members' emails (from `/memberships`).
- Requires `is_user_referenced_by_email=True` on the datasource config.
- Fail-closed: if memberships cannot be read for a room, skip its docs rather than expose them broadly.

## Unknowns / risks
- Production token scope determines room visibility (bot membership vs org-wide).
- Rate limits: honor 429 + Retry-After. Cost scales with total message count.
- direct (DM) rooms excluded by default in v1.
- Attachment binaries not fetched in v1 (URLs recorded only).
