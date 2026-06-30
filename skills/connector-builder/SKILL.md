---
name: connector-builder
description: Build Glean Indexing SDK connectors from source-system documentation. Use when planning, generating, validating, or evaluating a custom connector built with the Glean Indexing SDK.
---

# Connector Builder

Use this skill as the top-level workflow for building Glean Indexing SDK connectors with an AI coding agent. It coordinates source documentation confirmation, API exploration, user-confirmed planning, local validation, generation, and evaluation.

## When To Use

Use this skill when the user wants to build, evaluate, or iterate on a connector for a third-party datasource.

## Rules

- Do not generate code until API exploration is complete and the user confirms the connector plan.
- Prefer official source-system docs over prior connector implementations.
- Persist repeated context in the connector folder's `.glean/` directory, not only in the chat. For example, a Webex connector should keep artifacts under `<connector-folder>/.glean/`, not a repo-level `.glean/`.
- Do not write connector implementation code until `connector_builder.py validate` passes.
- Redact secrets from any API call logs.
- The AI-building workflow supports full crawls only for now. SDK components may support incremental crawls, but incremental behavior needs developer attention and should be called out as follow-up work.

## Workflow

1. Identify official source-system API documentation. If links are not provided, search for candidates and ask the user to confirm them once. If no reliable docs can be found, stop and ask the user for API documentation, an OpenAPI spec, or sample API responses.
2. Ask the user for an API base URL and read-only test credentials/token. Explain that live read-only API probes materially improve connector quality because they verify auth, response shapes, pagination, rate limits, and permissions against the real API. If credentials are not provided, continue from documentation only and mark confidence gaps.
3. Create or identify the connector folder and create its `.glean/` directory.
4. Use the `connector-api-exploration` skill to inspect docs and, when credentials are available, run read-only API probes. Fill `<connector-folder>/.glean/source_investigation.md`, `<connector-folder>/.glean/api_inventory.md`, `<connector-folder>/.glean/api_endpoints.json`, and `<connector-folder>/.glean/api_calls_log.md`.
5. Enter planning mode. Draft `<connector-folder>/.glean/connector_plan.md` and ask the user to confirm scope before technical work. Capture:
   - each source API endpoint and how it will be used
   - which entities are in scope for the first version
   - full-crawl behavior and any incremental follow-up notes
   - test auth vs production auth
   - Glean-side upload/status endpoints from the `connector-push` skill
   - expected document count, average document size, freshness needs, source API limits, and recommended crawl frequency
   - push-layer-only vs full connector flow
   - deployment/hosting expectations
6. Mark the plan as confirmed only after user approval by setting `Status: confirmed`.
7. Revalidate before implementation:

```bash
python scripts/connector_builder/connector_builder.py validate <connector-folder>
```

8. Implement the data client and connector using the `connector-auth`, `connector-pull`, and `connector-push` skills. Post-validation code generation is handled by the agent following the skills, not by the local validator.
9. Evaluate with local checks first, then real source/Glean test runs when credentials are available.

## Required Artifacts

- `<connector-folder>/.glean/source_docs.json`: confirmed source-of-truth docs.
- `<connector-folder>/.glean/connector_plan.md`: user-confirmed product scope and constraints.
- `<connector-folder>/.glean/source_investigation.md`: auth, source model, sync, permission, and unknowns.
- `<connector-folder>/.glean/api_inventory.md`: cited endpoint catalog and API behavior summary.
- `<connector-folder>/.glean/api_endpoints.json`: structured endpoint list with `name`, `method`, `path`, and `purpose`.
- `<connector-folder>/.glean/api_calls_log.md`: redacted read-only probe log when live API calls are used.

## Evaluation

Evaluate connector quality by checking:

- Planning artifacts are confirmed and internally consistent.
- Generated Python compiles.
- Source fetch returns limited expected records with test credentials, if available.
- Transform/upload paths can push to a test Glean datasource, if credentials are available.
- Connector behavior matches the confirmed plan, especially full vs incremental crawl constraints.
