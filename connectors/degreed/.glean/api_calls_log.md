# Degreed API calls log

## 2026-07-14

No live API calls were made. The user chose documentation-only exploration and did not provide read-only credentials.

Planned minimum probes when credentials become available:

1. Request an OAuth token from `https://degreed.com/oauth/token` with the `content:read` scope. Persist only status, expiry shape, and redacted error details.
2. Request `GET https://api.degreed.com/api/v2/content?limit=2` and record the redacted response shape plus pagination and rate-limit headers.
3. Follow one `links.next` cursor to verify its exact representation and expiry behavior.

Credentials, authorization headers, bearer tokens, and customer content must not be persisted in this file.
