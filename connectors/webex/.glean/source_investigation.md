# Webex Source Investigation

Datasource: Cisco Webex (Messaging). Base URL `https://webexapis.com/v1`. Explored 2026-07-21 with a live admin personal access token against test org `stevesmith-7xdw`.

## Authentication
- **Exploration:** personal access token from developer.webex.com (this token has compliance scopes; all `/events` calls returned 200). Single `Authorization: Bearer <token>` header. Expires ~12h; non-production.
- **Production (org-wide compliance):** a **Compliance Officer** identity via OAuth **Integration** or **Service App**, with scopes: `spark-compliance:events_read` (org-wide message events), `spark-compliance:memberships_read` (cross-room ACL), and `spark:people_read` (identities). The account must hold the org **Compliance Officer** role.
- Required read scopes for V1: `spark-compliance:events_read`, `spark-compliance:memberships_read`, `spark:people_read`.

## Source data model
- **Room (space)**: container. `type` = `group` or `direct` (1:1). Has title, timestamps, owner/creator, team linkage, lock/visibility flags.
- **Message**: content unit inside a room. Body in `text` (+ optional `markdown`/`html`). May have `files[]` (attachments), `parentId` (threaded reply), mentions. Authored by a Person.
- **Membership**: join row between Person and Room; carries moderator/monitor flags. This is the ACL.
- **Person**: user identity (email, name, org, status, type person/bot/appuser).

## Sync model (CONFIRMED: org-wide compliance Events, 90-day window)
- **Primary source = compliance Events API** (`GET /events?resource=messages`). event.data carries the message content org-wide (all rooms, no membership needed).
- **Hard 90-day lookback limit** (verified: 1yr/3yr → 403 "only authorized to search within past 90 days"). ⇒ **coverage window = last 90 days**, rolling. Messages older than 90 days are NOT retrievable org-wide and are out of coverage (documented, accepted by user).
- **Deletions:** `type=deleted` events give message id + roomId → exclude/delete those docs; full-crawl stale deletion also prunes.
- **Edits:** `type=updated` events carry new text → keep latest text per message id.
- **Full crawl only:** each run re-scans the 90-day window, reconciles created/updated (latest) minus deleted, uploads as a full crawl. A partial/failed event scan is never finalized as a full crawl.
- **Incremental (follow-up, NOT V1):** persist a checkpoint (`from`=last run) and page only new events; deletion via delete events. Natural next step but developer-owned.

## Coverage decision (CONFIRMED)
- **Org-wide via compliance Events API**, rolling **90-day** window. All org spaces, regardless of connector-account membership.
- Rooms only surface if they had message activity within 90 days (event-driven discovery). Rooms silent for 90+ days won't appear — acceptable for a chat-search connector.
- Rejected alternatives: (a) account-visible `/rooms`+`/messages` = full history but only the account's rooms; (b) service account in all spaces = full history org-wide but heavy membership ops. User chose compliance Events.

## Permissions model (critical)
- Each message inherits its room's membership. Glean document ACL = the set of people in that room (from `GET /memberships?roomId=`).
- **Cross-room verified:** `GET /memberships?roomId=` returns HTTP 200 with members even for rooms the caller is NOT in (compliance) — so ACLs are available org-wide.
- Map membership `personEmail` → Glean user identities. Index People as Glean identities so ACLs resolve.
- `direct` rooms = 2 members; `group` rooms = N members.
- One Glean group per room; each message doc permitted to its room's group.

## Historical constraint (accepted)
- `GET /rooms` / `GET /messages` are membership-scoped (verified: cross-room `/messages` → 404). Org-wide content therefore comes only from the Events API, which is capped at 90 days.
- ⇒ Coverage window = last 90 days org-wide. Accepted by user ("90 days is fine").

## Load / volume (to refine with user)
- Cost model per full crawl: page all message events over 90 days (`/events?resource=messages`, created+updated+deleted) + `GET /memberships?roomId=` per discovered room + `GET /people` (paged).
- Rate limits: `429` + `Retry-After` (seconds). Connector must honor `Retry-After` and back off. Exact numbers undocumented.
- Event paging over 90 days dominates cost. In-memory reconciliation (message id → latest text, minus deleted) is the simple V1 approach; partition by day/room if memory becomes a concern (follow-up).

## Unknowns / open questions (resolved unless noted)
1. Coverage: **RESOLVED** — org-wide compliance Events, 90-day window.
2. Room types: **RESOLVED** — group + direct (1:1).
3. Attachments: **RESOLVED** — text only; event payload has no files, so attachments are out of V1 entirely (would need /messages enrichment, which is membership-scoped).
4. Threading: parentId is NOT present in event.data → threading unavailable via events in V1; each message is its own doc. (Follow-up if enrichment added.)
5. Volume/sizing: refine after first real 90-day crawl.
6. Production auth: **RESOLVED** — Compliance Officer via OAuth Integration/Service App with `spark-compliance:*_read` + `spark:people_read`.
7. OPEN (verify at deploy): confirm the production compliance account can read `/memberships` for rooms it isn't in (verified on the admin token here; re-confirm with the actual production Compliance Officer credential).
