# Webex Connector Plan

Status: confirmed

Datasource: **Cisco Webex (Messaging)** — `webex`
Owner: Ishan Chawla
Created: 2026-07-21
Source API base: `https://webexapis.com/v1` (all endpoints verified live against test org `stevesmith-7xdw`).

## 1. Goal & summary

Index Webex Messaging content **org-wide** into Glean so employees can search across all Webex spaces,
with per-message permissions so results respect who can see each space. V1 is a **full-crawl** connector
that sources message content from the Webex **compliance Events API** (all spaces, regardless of the
connector account's membership) over a rolling **90-day coverage window**, plus the people and room
memberships needed to enforce permissions.

## 2. Coverage model (org-wide, compliance) — confirmed

- **All org spaces**, regardless of connector-account membership, via `GET /events?resource=messages`.
- **90-day rolling coverage window** — hard Webex limit (verified: older lookback → `403 "only authorized
  to search within past 90 days"`). Messages older than 90 days are out of coverage. **User accepted
  ("90 days is fine").**
- Rooms are discovered from message events, so a room appears only if it had activity within 90 days.
- Rejected alternatives: account-visible `/rooms`+`/messages` (full history, but only the account's rooms);
  service account added to every space (full history org-wide, but heavy membership operations).

## 3. Source objects — scope decisions

| Source object | Webex API | V1 status | Notes |
|---|---|---|---|
| Message (document) | `GET /events?resource=messages` | **Included** | Org-wide. One Glean doc per message; body = event `data.text`. Both `group` and `direct` rooms. |
| Membership (permissions) | `GET /memberships?roomId=` | **Included** | Cross-room read verified (HTTP 200 for non-member rooms) → org-wide ACL. One Glean group per room. |
| Person (identity) | `GET /people`, `/people/me` | **Included** | Indexed as datasource users so ACLs resolve by email. |
| Room metadata | `GET /rooms` | **Metadata only** | Account-scoped; used to enrich titles where available. Not the content source. |
| Message deletions | `GET /events?...&type=deleted` | **Included** | Exclude/delete removed messages within the window. |
| Message edits | `GET /events?...&type=updated` | **Included** | Use latest text per message id. |
| Attachments / files | (not in event payload) | **Excluded** | Event `data` carries no `files`; `/messages` enrichment is membership-scoped → out of V1. |
| Threaded replies | (not in event payload) | **Excluded** | `parentId` not in event `data`; each message is its own doc. |
| Meetings / recordings / transcripts | (separate API) | **Excluded** | Out of confirmed scope. |

## 4. Crawl semantics (full crawl only)

- Each run scans the compliance Events API across the last 90 days:
  1. Collect `type=deleted` message ids (exclusion set).
  2. Page `type=created` + `type=updated` message events; keep the **latest text per message id**; drop ids in the exclusion set.
  3. For each room id seen, fetch `GET /memberships?roomId=` → that room's Glean group members.
  4. Fetch `GET /people` → datasource users.
- Upload as a **full crawl**: documents replace prior state; Glean full-crawl **stale-document deletion**
  removes messages that dropped out of the window or were deleted at the source.
- A partial/failed event scan is **never** finalized as a full crawl (would wrongly delete valid docs).
- **Incremental (follow-up, NOT V1):** persist `from`=last-successful-run and page only new events.

## 5. Endpoint → field mapping

**Message events** (`GET /events?resource=messages`): `data.id` (doc id), `data.roomId` (container + group), `data.roomType`, `data.text` (body), `data.personId`/`data.personEmail` (author), `data.created` (timestamp); event `type` (created/updated/deleted); event `created` (edit ordering).

**Memberships** (`GET /memberships?roomId=`): `personEmail`, `personId`, `personDisplayName`, `isModerator`, `roomId` → members of each room's Glean group (the ACL).

**People** (`GET /people`, `/people/me`): `id`, `emails`, `displayName`, `firstName`, `lastName`, `status`, `type` → datasource users keyed by primary email. `/people/me` = auth smoke test.

## 6. Search-relevant fields

- **Title:** `"<author display name> in <room title>"` (room title from `/rooms` metadata when available; else roomType + short room id).
- **Body:** message `data.text`.
- **URL:** space deep link (`https://web.webex.com/spaces/<roomId>` style) — best available; message-level deep links not exposed via events.
- **Author:** `personEmail` → resolved Glean user.
- **Timestamp:** `data.created` (createdAt/updatedAt).
- **Container:** room (title/id).
- **Metadata:** `roomType`, `roomId`, `personEmail`.

## 7. Permissions model

- One Glean **group per Webex room**; membership from `GET /memberships?roomId=` (verified org-wide readable).
- Each message document is permitted to its room's group (allow-list).
- **People** indexed as datasource users keyed by primary email so group members resolve to Glean users.

## 8. Auth

- Test auth: Webex personal access token from developer.webex.com (has compliance scopes), sent as `Authorization: Bearer <token>`; used for API exploration and local validation. Short-lived (~12h), non-production. Stored locally in `connectors/webex/.env` as `WEBEX_ACCESS_TOKEN` (gitignored, never committed).
- Production auth: a Compliance Officer identity via OAuth Integration (refreshable) or Service App, with scopes `spark-compliance:events_read`, `spark-compliance:memberships_read`, `spark:people_read`; supplied at runtime as `WEBEX_ACCESS_TOKEN` (or refreshable credential) via the deployment secret store. The account must hold the org Compliance Officer role.
- **Glean indexing auth:** `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`.

## 9. SDK usage

- SDK usage: full connector flow — source pull (compliance Events + memberships + people) plus Glean push (documents + identities). Streaming-style upload for documents to bound memory; identity upload for users, per-room groups, and memberships.
- **Full-crawl document upload:** bulk document replacement (drives stale-document deletion).
- **Identity upload:** full-crawl user replacement (`bulk_index_users`), group replacement (`bulk_index_groups`, one group per room), and membership replacement (`bulk_index_memberships`).
- **Datasource config:** register `webex` with a document object type for messages; declared object types match what documents emit.
- **Test upload:** a small `index_documents` batch (a handful of message docs) to a test datasource before the full run.

## 10. Glean-side status / debug checks (post-upload)

- `get_datasource_status` — overall upload/processing state of `webex`.
- `get_documents_status` — upload/index status + `permissionIdentityStatus` (only `UPLOADED`/`NOT_UPLOADED`/`UNKNOWN`) for a sample of message docs.
- `check_document_access` — verify a room member can access its messages and a non-member cannot.
- `debug_user` / `get_document_lifecycle_events` — ad hoc when a doc or user looks wrong.

## 11. Observability

- **Provider:** console structured logging (`ConsoleLoggerProvider`); metrics via no-op in prod, in-memory during local eval. `ConnectorObservability` passed into the uploader.
- **Lifecycle logs:** crawl started / completed / failed.
- **Fetch counts:** message events scanned (created/updated/deleted), unique messages after reconciliation, rooms discovered, memberships fetched, people fetched.
- **Transform counts:** documents produced, messages skipped (empty text / deleted).
- **Upload metrics/events:** batch start/complete/fail, batch size, upload id; users/groups/memberships counts.
- **Evaluation:** status/debug checks in §10 after a test upload.
- **Secret redaction:** never log `WEBEX_ACCESS_TOKEN`, `GLEAN_INDEXING_API_TOKEN`, Authorization headers, or raw message text at error level.

## 12. Volume, freshness & schedule

- **Freshness:** daily is acceptable (confirmed).
- **Volume:** unknown in production; bounded by 90-day event volume. Cost per run = paged message events over 90 days + `GET /memberships?roomId=` per discovered room + paged `GET /people`.
- **Recommended full-crawl frequency:** **daily**, off-peak. Proposed cron `17 3 * * *` (03:17). Honors `Retry-After` on 429.
- **Follow-up:** refine schedule + resources after observing a real 90-day crawl's duration and doc count.

## 13. Deployment (customer-hosted, GCP/GKE)

- **In scope:** yes — customer-hosted on **GCP/GKE** via `glean-deploy`.
- **Cloud:** GCP. **Region / project / cluster / namespace / Artifact Registry repo:** to be provided by user at deploy time (namespace defaults to `default`).
- **Schedule:** Kubernetes CronJob, daily (`17 3 * * *`).
- **Resources (initial estimate, to refine):** ~ **1 vCPU / 2 GiB**; adjust after first real crawl (in-memory reconciliation over 90 days is the main memory driver).
- **Runtime secrets:** `WEBEX_ACCESS_TOKEN` (compliance credential), `GLEAN_SERVER_URL`, `GLEAN_INDEXING_API_TOKEN` — via `glean-deploy secrets upload`, never committed.
- **Indexing mode:** FULL.
- Cloud-mutating commands run only after explicit user confirmation and pre-deployment revalidation (incl. confirming the production Compliance Officer credential can read `/memberships` cross-room and `/events` org-wide).

## 14. Known follow-ups (developer-owned, not in V1)

1. Incremental crawl via Events API checkpoint (`from`=last run) with delete-event handling.
2. Message enrichment (markdown, files, threading) — requires membership-scoped `/messages` or a different mechanism.
3. History beyond 90 days (only possible via account-in-space membership, not compliance events).
4. Memory scaling of reconciliation (partition by day/room) for very large orgs.
5. Production OAuth Integration / Service App token refresh handling.
6. Refine crawl schedule + GKE resource sizing after first real crawl.

## 15. Out of scope (V1)

- Webex Meetings, recordings, transcripts, calling.
- Attachments/file content, threaded-reply structure, message-level deep links.
- Real-time/webhook indexing.
- Messages older than the 90-day window.
