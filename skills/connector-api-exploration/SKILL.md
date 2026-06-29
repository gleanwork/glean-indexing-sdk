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
- Optional credentials or env file for read-only testing.
- Connector workspace directory containing `.glean/`.
- User requirements from the confirmed connector plan, if already available.

## Outputs

Write outputs to the connector workspace:

- `.glean/api_inventory.md`
- `.glean/api_endpoints.json`
- `.glean/api_calls_log.md`
- `.glean/source_investigation.md`

## Exploration Rules

- Prefer official vendor docs. Use internal or prior connector examples only as supporting evidence.
- Cite the source doc URL or local file for every endpoint and important behavior claim.
- Use only read-only API calls unless the user explicitly approves otherwise.
- Redact credentials in all persisted commands, headers, responses, and logs.
- Record skipped endpoints and why they were skipped.
- Do not claim incremental sync support unless the API exposes a reliable updated/deleted signal for the relevant entity.
- Do not hide uncertainty. Put unresolved questions in `.glean/source_investigation.md`.

## Workflow

1. Read confirmed docs from `.glean/source_docs.json` and any additional user-provided docs.
2. Identify connector-relevant objects: content, identities, memberships, permissions, attachments, and deleted/stale records.
3. Enumerate endpoints needed for each object. Capture:
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
4. If credentials are available, run minimal read-only probes against representative endpoints.
5. Write a human-readable endpoint catalog to `.glean/api_inventory.md`.
6. Write the structured endpoint inventory to `.glean/api_endpoints.json`.
7. Write read-only probe results to `.glean/api_calls_log.md` with secrets redacted.
8. Update `.glean/source_investigation.md` with auth, sync, permission, and unknowns.

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
