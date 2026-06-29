---
name: connector-builder
description: Build Glean Indexing SDK connectors from source-system documentation. Use when planning, generating, validating, or evaluating a custom connector built with the Glean Indexing SDK.
---

# Connector Builder

Use this skill as the top-level workflow for building Glean Indexing SDK connectors with an AI coding agent. It coordinates source documentation confirmation, API exploration, user-confirmed planning, local validation, generation, and evaluation.

## When To Use

Use this skill when the user wants to build, evaluate, or iterate on a connector for a third-party datasource.

## Rules

- Stay in planning mode until the user confirms the connector plan.
- Prefer official source-system docs over prior connector implementations.
- Persist repeated context in the connector workspace's `.glean/` directory, not only in the chat.
- Do not write connector implementation code until `connector_builder.py validate` passes.
- Redact secrets from any API call logs.

## Workflow

1. Confirm official source-system documentation with the user.
2. Use the `connector-api-exploration` skill to inspect docs and, when credentials are available, run read-only API probes.
3. Initialize the connector workspace:

```bash
python scripts/connector_builder/connector_builder.py init <datasource> --display-name "<Display Name>" --doc-url "<confirmed-doc-url>"
```

4. Draft `.glean/connector_plan.md` and ask the user to confirm scope before technical work. Capture entities, crawl mode, permissions, push-layer-only vs full connector flow, and deployment expectations.
5. Fill `.glean/source_investigation.md`, `.glean/api_inventory.md`, and `.glean/api_endpoints.json` from confirmed docs and API exploration.
6. Mark the plan as confirmed only after user approval by setting `Status: confirmed`.
7. Revalidate before implementation:

```bash
python scripts/connector_builder/connector_builder.py validate
```

8. Generate the snippet skeleton:

```bash
python scripts/connector_builder/connector_builder.py generate <datasource> --display-name "<Display Name>"
```

9. Implement the data client and connector using follow-up skills for pull, push, auth, and observability as they become available.
10. Evaluate with local checks first, then real source/Glean test runs when credentials are available.

## Required Artifacts

- `.glean/source_docs.json`: confirmed source-of-truth docs.
- `.glean/connector_plan.md`: user-confirmed product scope and constraints.
- `.glean/source_investigation.md`: auth, source model, sync, permission, and unknowns.
- `.glean/api_inventory.md`: cited endpoint catalog and API behavior summary.
- `.glean/api_endpoints.json`: structured endpoint list with `name`, `method`, `path`, and `purpose`.
- `.glean/api_calls_log.md`: redacted read-only probe log when live API calls are used.

## Evaluation

Evaluate connector quality by checking:

- Planning artifacts are confirmed and internally consistent.
- Generated Python compiles.
- Source fetch returns limited expected records with test credentials, if available.
- Transform/upload paths can push to a test Glean datasource, if credentials are available.
- Connector behavior matches the confirmed plan, especially full vs incremental crawl constraints.
