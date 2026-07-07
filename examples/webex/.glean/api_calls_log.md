# Webex Read-Only API Probe Log

Date: 2026-07-06. Auth: `Authorization: Bearer <REDACTED>` (read-only admin token, session-only).
All calls are read-only GETs against `https://webexapis.com/v1`. Token redacted throughout.

| # | Request | Status | Observations |
|---|---|---|---|
| 1 | `GET /people/me` | 200 | Token valid. Owner `admin@<REDACTED-org>.wbx.ai`, type=person, org present. |
| 2 | `GET /rooms?max=5` | 200 | 5 rooms; `Link: rel="next"` present (cursor pagination). Types: group, direct. |
| 3 | `GET /messages?roomId=<room0>&max=3` | 200 | Messages: id, roomId, roomType, text, personId, personEmail, created. |
| 4 | scan `/messages?roomId=<each>&max=10` across 14 rooms | 200 | 41 messages; optional html, files, mentionedPeople, parentId. 4 had html, 2 had files. |
| 5 | `GET /memberships?roomId=<room0>&max=3` | 200 | Members: personEmail, personDisplayName, isModerator; `Link: rel="next"` present. |

No 429/rate-limit responses encountered. No mutating calls made. Token stored only in `/tmp/webex_token` (chmod 600), to be deleted after the build.
