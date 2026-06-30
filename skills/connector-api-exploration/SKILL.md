---
name: connector-api-exploration
description: Explore third-party datasource API docs and read-only endpoints for a Glean Indexing SDK connector. Use before connector planning or generation to produce a cited API inventory and source investigation.
---

# Connector API Exploration

Use this skill before connector implementation. Its job is to turn confirmed source documentation into connector-ready API artifacts.

## Inputs

- Datasource name.
- Confirmed docs URLs, files, or local docs directory.
- API base URL, if known.
- Optional credentials, token, or env file for read-only testing.
- Connector workspace directory containing `.glean/`.
- User requirements or rough connector goal, if already available.

## Outputs

Write outputs to the connector workspace:

- `.glean/api_inventory.md`
- `.glean/api_endpoints.json`
- `.glean/api_calls_log.md`
- `.glean/source_investigation.md`
- `.glean/external_docs/` when documentation is fetched or copied locally.

## Exploration Rules

- Prefer official vendor docs. Use internal or prior connector examples only as supporting evidence.
- If API documentation links are missing, search for candidate official docs and ask the user to confirm them once.
- If no reliable docs can be found, stop and ask the user for API documentation, an OpenAPI spec, or sample request/response payloads.
- Cite the source doc URL or local file for every endpoint and important behavior claim.
- Ask for an API base URL and read-only token/credentials. Explain that live API probes produce much better connector quality because they verify auth, response fields, pagination, rate limits, and permissions against real responses.
- If credentials are not provided, proceed from documentation only and mark the lower-confidence areas explicitly.
- Use only read-only API calls unless the user explicitly approves otherwise. Default to GET requests.
- Redact credentials in all persisted commands, headers, responses, and logs.
- Record skipped endpoints and why they were skipped.
- Do not claim incremental sync support unless the API exposes a reliable updated/deleted signal for the relevant entity.
- Do not hide uncertainty. Put unresolved questions in `.glean/source_investigation.md`.

## Workflow

1. Read confirmed docs from `.glean/source_docs.json` and any additional user-provided docs.
2. If docs are URLs, fetch or copy the relevant documentation into `.glean/external_docs/` so later planning can cite local files or stable URLs.
3. Identify connector-relevant objects: content, identities, memberships, permissions, attachments, and deleted/stale records.
4. Build a complete endpoint inventory before narrowing implementation scope. Capture:
   - name
   - method
   - path
   - purpose
   - auth/scopes
   - pagination
   - rate limits
   - incremental filters
   - permission fields
   - deletion signals
   - source citation
5. If credentials are available, run minimal read-only probes against endpoints needed for the first connector version. For each probe, log the redacted request, status, headers relevant to rate limits/pagination, and representative response shape.
6. If credentials are unavailable or a call fails, document the gap and fall back to docs-only analysis.
7. Write a human-readable endpoint catalog to `.glean/api_inventory.md`.
8. Write the structured endpoint inventory to `.glean/api_endpoints.json`.
9. Write read-only probe results to `.glean/api_calls_log.md` with secrets redacted.
10. Update `.glean/source_investigation.md` with auth, sync, permission, load, and unknowns.

## Live Probe Guidance

When the user provides credentials:

- Test authentication first with the smallest safe endpoint.
- Prefer small page sizes and narrow filters.
- Probe list and detail endpoints for each in-scope entity when available.
- Capture complete response shape, including nested fields that may affect mapping.
- Capture pagination tokens, cursors, link headers, and rate-limit headers.
- Never log raw bearer tokens, API keys, cookies, or secrets. Use `<REDACTED>`.

When credentials are not provided:

- Do not block the workflow if documentation is sufficient.
- Clearly mark docs-only findings and unsupported assumptions.
- Ask the user to provide credentials later if response shape, pagination, permission, or auth details are ambiguous.

## Endpoint JSON Shape

Each endpoint in `.glean/api_endpoints.json` must include:

```json
{
  "name": "List rooms",
  "method": "GET",
  "path": "/v1/rooms",
  "purpose": "Fetch rooms to index as documents"
}
```

Add optional fields when known:

- `source`
- `required_scopes`
- `pagination`
- `rate_limit_notes`
- `incremental_filter`
- `response_fields`
- `permission_fields`
- `deletion_behavior`

## Handoff To Connector Builder

After exploration, run:

```bash
python scripts/connector_builder/connector_builder.py validate
```

If validation fails, update the `.glean/` artifacts before implementation. Do not generate connector code until validation passes.
