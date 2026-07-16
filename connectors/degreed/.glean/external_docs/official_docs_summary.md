# Degreed official API documentation summary

Sources confirmed by the user on 2026-07-14:

- [API Reference](https://developer.degreed.com/reference/overview)
- [Getting Started with the API](https://developer.degreed.com/docs/getting-started-with-the-api)
- [Authentication Guide](https://developer.degreed.com/docs/authentication)
- [Pagination](https://developer.degreed.com/docs/pagination)
- [Get All Content](https://developer.degreed.com/reference/get_api-v2-content)
- [Get a Specific Content Item](https://developer.degreed.com/reference/get_api-v2-content-id)

## Confirmed behavior

- US production API base URL: `https://api.degreed.com`.
- US production OAuth token URL: `https://degreed.com/oauth/token`.
- Authentication uses OAuth 2.0 client credentials. The token request is form encoded and includes `grant_type=client_credentials`, `client_id`, `client_secret`, and a comma-delimited `scope`.
- Catalog reads require `content:read` or `content:write`; the connector will request only `content:read`.
- `GET /api/v2/content` returns all non-obsolete content for the current organization and exposes the fields needed for a Glean document: ID, title, summary, source URL, Degreed URL, content type, provider, language, timestamps, image, skills, visibility, and groups with access.
- Pagination uses `limit` and `next`. The maximum page size is 1,000. Degreed snapshots the result set, and the pagination cursor expires if no subsequent request is made within two minutes.
- Restricted content is excluded unless `filter[include_restricted]=true`. The first version will leave this false and index organization-visible content only.
- The API supports `filter[modified_after]`, but the AI-built workflow is full-crawl only. Incremental crawling is deferred.

## Documentation-only limitations

No live credentials were supplied. Exact production response variations, rate-limit headers, token error payloads, and behavior for very large catalogs have not been probed.
