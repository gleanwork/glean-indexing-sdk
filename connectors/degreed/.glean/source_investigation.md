# Degreed source investigation

## Scope

The first version is a full-crawl connector for Degreed catalog learning content. It targets US production at `https://api.degreed.com` and excludes pathways, skill plans, users, learning activity, and restricted content.

## Authentication

- Test auth: Documentation-only exploration; no test credentials or live token were used.
- Production auth: OAuth 2.0 client credentials using `DEGREED_CLIENT_ID` and `DEGREED_CLIENT_SECRET`; request an in-memory bearer token from `https://degreed.com/oauth/token`.
- Required scope: `content:read`.
- Optional tenant setting: `DEGREED_ORGANIZATION_CODE` maps to `X-Degreed-Organization-Code` for Global Admin Tool organizations.
- Secrets: source credentials and access tokens must never be written to artifacts or logs.

The production connector should obtain and cache a token in memory. Degreed documents a default 60-day token lifetime, but the implementation should honor `expires_in` and renew before expiry. The documented refresh token is not useful to external API clients.

## Source model

`GET /api/v2/content` returns JSON:API-like records under `data`. Each record has:

- a stable Degreed `id`;
- searchable attributes including title, summary, type, provider, language, and duration;
- source and Degreed UI URLs;
- creation, modification, and publication timestamps;
- image and skill relationship metadata;
- visibility and group-access fields.

The first version maps one Degreed content record to one Glean document. Degreed's ID is the Glean document ID, and `degreed-url` is preferred as the document view URL with `url` as fallback.

## Pagination and sync

- Full crawl: `GET /api/v2/content?limit=1000`, followed by each `links.next` cursor until absent.
- Cursor constraint: the snapshot expires after two minutes of inactivity, so subsequent pages must be fetched promptly.
- Incremental signal: `filter[modified_after]` exists, but version 1 intentionally does not implement incremental crawling.
- Deletion behavior: the endpoint excludes obsolete content. A complete Glean bulk replacement makes missing or obsolete records stale.
- Failure behavior: an interrupted crawl must not finalize a partial full upload.

## Permissions

The API can expose restricted content and group IDs, but doing so safely would require a user/group/membership identity crawl and source-to-Glean permission mapping. Version 1 leaves `filter[include_restricted]` false and indexes organization-visible content only. This avoids making restricted items broadly searchable.

## Load and rate limits

Degreed documents a maximum page size of 1,000 but no numeric request limit on the reviewed pages. The implementation should honor `Retry-After`, retry `429` and transient `5xx` responses with bounded backoff, and keep successful pagination moving within the two-minute cursor window.

Expected document count, average summary size, and concrete freshness requirements are not known. The draft plan proposes a daily full crawl and configurable timeouts; these assumptions require user confirmation.

## Documentation-only confidence gaps

- Exact production response variations and nullable-field behavior were not probed.
- Whether `links.next` is always a full URL versus a token is not live-verified.
- Rate-limit headers and numeric limits are unknown.
- The catalog size and full-crawl duration are unknown.
- Global Admin Tool deployments may require `X-Degreed-Organization-Code`.
- The branch is based on the repository's `feature/v0-workstream` stack, which supplies the connector-builder validator and the SDK `recipes.pull` and `push` packages used by the implementation.
