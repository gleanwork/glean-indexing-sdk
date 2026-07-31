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
- Connector folder containing `.glean/`.
- User requirements or rough connector goal, if already available.

## Outputs

Write outputs to the connector folder:

- `<connector-folder>/.glean/api_inventory.md`
- `<connector-folder>/.glean/api_endpoints.json`
- `<connector-folder>/.glean/api_calls_log.md`
- `<connector-folder>/.glean/source_investigation.md`
- `<connector-folder>/.glean/external_docs/` when documentation is fetched or copied locally.

## Exploration Rules

- Prefer official vendor docs. Use internal or prior connector examples only as supporting evidence.
- If API documentation links are missing, search for candidate official docs and ask the user to confirm them once before treating them as source of truth.
- If the user provided documentation links, attempt those links first. If they cannot be fetched or read, stop and ask the user for an OpenAPI spec, copied docs, exported docs, or sample request/response payloads.
- Do not proceed from model general knowledge. A statement like "API specifics are from general knowledge, not verified docs" is a blocker, not acceptable evidence.
- If normal document fetching fails because docs are JavaScript-rendered, browser/Playwright extraction may be used as a bounded fallback. Try it once for the relevant docs; if it loops, requires login, or does not quickly produce useful content, stop and ask the user for an OpenAPI spec or copied docs.
- Cite the source doc URL or local file for every endpoint and important behavior claim.
- Ask for an API base URL and token/credentials. Recommend providing credentials because live API probes produce much better connector quality by verifying auth, response fields, pagination, rate limits, and permissions against real responses.
- If credentials are not provided, proceed from documentation only and mark the lower-confidence areas explicitly.
- Use only read-only API calls unless the user explicitly approves otherwise. Default to GET requests.
- Redact credentials in all persisted commands, headers, responses, and logs.
- Record skipped endpoints and why they were skipped.
- Do not claim incremental sync support unless the API exposes a reliable updated/deleted signal for the relevant entity.
- Investigate coverage before asking the user to choose it. Determine what each relevant API and credential type can actually retrieve: only content visible to the authenticated account, a configurable subset, or organization-wide content. Look for documented admin, audit, export, compliance, or events APIs that broaden coverage, and record their required roles, scopes, licensing, retention windows, and other constraints. Mark each coverage option as feasible, infeasible, or unverified from the available evidence.
- Do not hide uncertainty. Put unresolved questions in `.glean/source_investigation.md`.

## API Exploration Steps

1. Read confirmed docs from `<connector-folder>/.glean/source_docs.json` and any additional user-provided docs.
2. If docs are URLs, fetch or copy the relevant documentation into `<connector-folder>/.glean/external_docs/` so later planning can cite local files or stable URLs.
3. Identify connector-relevant objects from the user's exploration-scope answer and from the docs: containers, content records, comments/messages, files/attachments, users, groups, memberships, permissions, and deleted/stale records.
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
   - coverage boundary and any broader-coverage alternative
   - source citation
5. If credentials are available, run minimal read-only probes against endpoints needed for the first connector version. For each probe, log the redacted request, status, headers relevant to rate limits/pagination, and representative response shape.
6. If credentials are unavailable or a call fails, document the gap and fall back to docs-only analysis.
7. Write a human-readable endpoint catalog to `<connector-folder>/.glean/api_inventory.md`.
8. Write the structured endpoint inventory to `<connector-folder>/.glean/api_endpoints.json`.
9. Write read-only probe results to `<connector-folder>/.glean/api_calls_log.md` with secrets redacted.
10. Update `<connector-folder>/.glean/source_investigation.md` with auth, coverage options and feasibility, sync, permission, load, and unknowns.

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

Each endpoint in `<connector-folder>/.glean/api_endpoints.json` must include:

```json
{
  "name": "List records",
  "method": "GET",
  "path": "/v1/records",
  "purpose": "Fetch source records to index as documents"
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
- `coverage`
- `coverage_requirements`

## Completion Criteria

This skill is complete when the output files above contain a cited endpoint inventory, structured endpoint JSON, evidence-backed coverage options, source investigation notes, and redacted live-probe notes when credentials were available. The top-level `connector-builder` skill owns planning, validation, and implementation sequencing.
