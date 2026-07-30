# Webex Connector — Evaluation Notes

## E2E full-crawl smoke run (real Webex fetch + mocked Glean push)

Date: 2026-07-21. Ran `run_connector(WebexConnector(...))` against the live Webex
compliance API (test org `stevesmith-7xdw`) with the Glean push layer mocked.
Lookback bounded to 30 days for the run.

Result: **PASS — crawl completed successfully.**

| Check | Result |
|---|---|
| `GET /events` (org-wide messages) | 200; reconciled 16 created + 0 updated − 1 deleted = **15 live** |
| Rooms discovered from events | **13** |
| `GET /memberships?roomId=` per room | 200 for all 13 rooms |
| Datasource configured (`datasources.add`) | called once, `name=webex`, object_definitions=`['Message']` |
| Users pushed | 7 |
| Groups pushed (one per room) | 13 |
| Memberships pushed (per-group) | 37 |
| Documents pushed | 15 |
| Docs missing permissions | 0 |
| Docs missing body | 0 |

Sample document:
- `object_type=Message`, `id=<webex message id>`
- `title="steve.smith@salessavvy.net in Webex space"`
- `body="testing if this message appears on SERP"`
- `author.email=steve.smith@salessavvy.net`, `created_at=1782142895`
- `view_url=https://web.webex.com/spaces/<roomId>`
- `permissions.allowed_groups=["webex-room-<roomId>"]`

## Reconciliation verified
Single chronological pass over message events: created/updated set latest text,
deleted removes. The 1 deleted event correctly reduced 16 → 15 live docs.

## Static checks
- `ruff check`: passed. `ruff format --check`: all formatted. `pyright`: 0 errors / 0 warnings.

## Known dev-environment note (not a connector defect)
The dev sandbox injects an HTTPS proxy (`HTTPS_PROXY=127.0.0.1:...`, Socket
Firewall) with a self-signed CA that `httpx` (certifi) rejects. Direct TLS to
Webex is valid (IdenTrust chain). For local runs either:
- trust the firewall CA (`GIT_PROXY_SSL_CAINFO` points to `socketFirewallCa.crt`), or
- pass `http_client=httpx.Client(trust_env=False)` to `WebexComplianceDataClient`
  (the client now supports an `http_client` passthrough for custom TLS/CA/proxy).
Production (GKE) has no such proxy; the default client works there.

## Not yet done
- Regression unit tests (deferred per workflow until E2E confirmed — now confirmed).
- GKE deployment via `glean-deploy`.

## Real Glean upload + status checks (dev backend)

Date: 2026-07-21. Target: `glean-dev-be.glean.com`. Datasource name `webexsmoke`
(the name `webex` was already tombstoned on this dev instance — "deleted and
disposed" — so a fresh alphanumeric name was used; datasource names must be
alphanumeric only). Connector now supports `WEBEX_DATASOURCE_NAME` / `name=` override.

Result: **PASS — all uploads returned HTTP 200.**

| Call | Result |
|---|---|
| `adddatasource` | 200 (datasource configured) |
| `bulkindexusers` (7) | 200 |
| `bulkindexgroups` (13) | 200 |
| `bulkindexmemberships` (13 groups) | 200 each |
| `bulkindexdocuments` (15) | 200 |
| Crawl | completed successfully |

Post-upload status:
- `get_datasource_status` → HTTP 200; upload `status: SUCCESSFUL`, `processingState: "UPLOAD COMPLETED"`.
- `get_documents_status` → HTTP 200; sample doc present (`docId`, `objectType: Message`).
- `check_document_access` → HTTP 200; endpoint works. Immediately post-upload,
  access returns `has_access=False` for BOTH member and non-member — permission
  identities are processed asynchronously and had not resolved yet (eventual
  consistency), not a wrong grant. Re-check after Glean finishes permission
  processing to confirm member=True / non-member=False.

SDK note: `StatusClient.get_datasource_status` / `get_documents_status` raised
`GleanError: Unexpected response received: Status 200` — the generated client's
response model didn't match the (valid) 200 body. The HTTP calls succeeded and
the bodies contained the expected data (verified via direct curl). Generated-client
deserialization quirk, not a connector defect.
