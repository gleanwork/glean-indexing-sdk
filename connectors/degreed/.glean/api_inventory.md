# Degreed API inventory

This inventory is based on official documentation only. No live API calls were made.

## Authentication

### Create access token

- Method and URL: `POST https://degreed.com/oauth/token`
- Purpose: exchange a Degreed OAuth client ID and client secret for a bearer token.
- Encoding: `application/x-www-form-urlencoded`.
- Parameters: `grant_type=client_credentials`, `client_id`, `client_secret`, and comma-delimited `scope`.
- Minimum connector scope: `content:read`.
- Source: [Authentication Guide](https://developer.degreed.com/docs/authentication).

The connector should cache the access token in memory until shortly before expiry and must never log credentials or token values.

## In-scope catalog endpoints

### List all content

- Method and path: `GET /api/v2/content`
- Purpose: retrieve all non-obsolete catalog content for the authenticated organization.
- Scope: `content:read` or `content:write`; use `content:read`.
- Pagination: request up to 1,000 items using `limit`. Follow the token in `links.next` with the `next` query parameter. The snapshotted result set expires if paging pauses for two minutes.
- Full-crawl filters: do not send date filters. Leave `filter[include_restricted]` false so restricted content is excluded.
- Optional incremental signal: `filter[modified_after]` and `filter[modified_before]` accept `yyyy-mm-dd`; not used in version 1.
- Content types returned by the general endpoint include courses, events, videos, assessments, podcasts, books, tasks, and articles represented in the response's `content-type`.
- Important document fields: `id`, `title`, `summary`, `url`, `degreed-url`, `content-type`, `provider`, `language`, `image-url`, `learning-minutes`, `created-at`, `modified-at`, `publish-date`, and skill relationships.
- Permission fields: `visibility`, `groups-with-access`, and `groups-with-access-ids`.
- Deletion signal: obsolete records are omitted. A successful full-crawl bulk replacement on Glean removes records no longer returned.
- Sources: [Get All Content](https://developer.degreed.com/reference/get_api-v2-content) and [Pagination](https://developer.degreed.com/docs/pagination).

### Get a specific content item

- Method and path: `GET /api/v2/content/{id}`
- Purpose: focused diagnostics or verification of one source item.
- Scope: `content:read` or `content:write`.
- Limitation: the generic detail endpoint omits some type-specific attributes. The list endpoint already returns the fields required by the first connector version.
- Source: [Get a Specific Content Item](https://developer.degreed.com/reference/get_api-v2-content-id).

## Related endpoints evaluated but out of scope

- Type-specific endpoints under `/api/v2/content/{articles|assessments|books|courses|events|podcasts|videos}` are skipped because the general content endpoint supplies the fields required for search and avoids one crawl per type.
- `/api/v2/pathways` and `/api/v2/skill-plans` are skipped because the user selected catalog content only.
- `/api/v2/users`, group, and membership endpoints are skipped in version 1. Restricted content is also excluded, so no Degreed ACL identity crawl is required.
- Learning activity endpoints such as completions, required learning, and accomplishments are skipped because they are user activity, not catalog documents.
- Write and delete endpoints are skipped because the source side of this connector is read-only.

## Rate limits and reliability

The reviewed official pages do not publish a numeric rate limit. The connector should retry `429` and transient `5xx` responses, honor `Retry-After`, use bounded exponential backoff, and avoid sleeping between successful pages because Degreed's pagination cursor expires after two minutes.

## Confidence gaps

Without a live read-only probe, the exact `links.next` URL/token representation, nullable field combinations, response headers, and production rate-limit behavior remain unverified. Unit tests should cover full next URLs, absent next links, nullable attributes, token refresh, and transient failures.
