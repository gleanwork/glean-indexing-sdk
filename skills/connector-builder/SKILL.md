---
name: connector-builder
description: Build Glean Indexing SDK connectors from source-system documentation. Use when planning, generating, validating, or evaluating a custom connector built with the Glean Indexing SDK.
---

# Connector Builder

Use this skill as the top-level workflow for building Glean Indexing SDK connectors with an AI coding agent. It coordinates source documentation confirmation, API exploration, user-confirmed planning, local validation, generation, and evaluation.

## When To Use

Use this skill when the user wants to build, evaluate, or iterate on a connector for a third-party datasource.

## Mental Model

Follow this loop: ask scope -> plan -> implement -> local validation -> deploy if requested -> inspect real deployed logs -> fix and re-run validation if needed.

## Rules

- Do not generate code until API exploration is complete and the user confirms the connector plan.
- Prefer official source-system docs over prior connector implementations.
- Persist repeated context in the connector folder's `.glean/` directory, not only in the chat. Connector artifacts must live under `<connector-folder>/.glean/`, not a repo-level `.glean/`.
- Do not write connector implementation code until `connector_builder.py validate` passes.
- Redact secrets from any API call logs.
- The AI-building workflow generates full-crawl connectors only. Do not implement incremental crawl in generated code; record it only as developer follow-up after full crawl works end-to-end.
- Every full crawl must be complete and self-contained: a single full-crawl run must bring Glean to the correct end state entirely on its own. That means indexing every in-scope document that currently exists at the source, and — via full-crawl stale-document deletion — removing everything that no longer exists, including source-side deletions and items that have aged out of any coverage window. Never rely on incremental crawl to eventually delete, update, or reconcile anything; correctness must not depend on it. If the source only exposes deletions or edits as events (e.g. a compliance/audit/event feed), reconcile them inside the full crawl (for example, index "created minus deleted" over the window, and use the latest event's content for edits) so the crawl output already reflects them — do not defer them. Incremental crawl, if it is ever added, is purely a freshness/cost optimization layered on top of an already-correct full crawl. When you record deferred follow-ups, incremental may only speed up or cheapen what the full crawl already does correctly; anything a full crawl needs for a correct end state (deletions, edits, permission changes) belongs in the full crawl, not in a deferred incremental note.
- Trace every scope decision to its concrete, user-visible behavior and state that behavior plainly to the user during planning — do not leave it as a bare exclusion footnote. For each exclusion, deferral, coverage window, permission limit, or crawl-frequency choice, spell out what an end user will actually observe in Glean. "Deletes excluded" is not acceptable on its own; the reviewable statement is the consequence, e.g. "a message deleted in the source keeps appearing in Glean search for up to ~90 days, until its create event ages out of the window." Likewise: an edited message shows its original text until re-crawled; a revoked space member can still find messages until the next full crawl; content older than the coverage window is never searchable. Record these consequences in `connector_plan.md` and confirm them with the user, so they are decisions the user signed off on, not surprises discovered after deployment.
- Do not add unit tests during initial connector generation. First get a full-crawl connector compiling and passing an end-to-end smoke run; add focused regression tests only after the E2E path is confirmed.
- Always ask the user connector data-model questions before drafting the connector plan. Do not infer final scope from API docs alone.
- Surface auth-gated coverage tradeoffs as explicit user decisions, never as silent plan footnotes. When exploration shows the default endpoints are permission- or membership-scoped and a broader admin/compliance/export API exists for full-org coverage, present that choice to the user before drafting the plan. Do not silently default to whatever the connector account can natively see.
- When documents are permission-trimmed (non-anonymous `allowed_users`/`allowed_groups`), treat indexing the ACL identities as part of the connector, not an afterthought: plan how ACL users are discovered and index them before documents. Streaming connectors do NOT auto-index identities via `get_identities()`, so this must be implemented explicitly (see the `connector-push` skill). Verify it with `check_document_access` — not just a successful upload — before calling the connector done. If you hit `400 ... User <email> not found for datasource ..., please index the user before adding permissions`, fix the identity ordering; do not downgrade to anonymous/all-users access to make the upload pass.
- After making connector or harness implementation changes, use the `connector-testing` skill and ask once whether to proceed to the testing step.
- At the start of a connector-building session, check whether this plugin is up to date: compare the locally installed version (`claude plugin list`) against the latest in the open-source repo (the `version` in `package.json` on `main` in `gleanwork/glean-indexing-sdk`, falling back to `feature/v0-workstream` if `package.json` is unavailable on `main`). If they differ, tell the user an update is available and give them the exact commands from the README's "Updating the plugin" section (`git pull && npm run build:plugins && claude plugin marketplace update glean-indexing-sdk-agent-plugin && claude plugin update glean-connector-builder@glean-indexing-sdk-agent-plugin`). These commands are for Claude Code; for other AI tools, tell the user the equivalent plugin-update commands for their environment. If the versions match or the check fails, continue without interrupting the user.

## Workflow

1. Ask the pre-exploration questions needed to avoid guessing:
   - Which official source API docs should be used? If the user did not provide docs, search for candidate official docs and ask the user to confirm them once. If no reliable docs can be found, stop and ask for API docs, an OpenAPI spec, or sample API responses.
   - Can the user provide an API base URL and test credentials/token? Recommend this option because live probes materially improve connector quality. Docs-only mode is a fallback, not the preferred path.
   - Which source objects should be considered for indexing and permissions? Ask explicitly about containers, documents/messages/records, comments, files/attachments, users, groups, memberships, and permissions. Treat the answer as exploration scope, not final V1 scope.
   - What coverage does the connector need: only what the connector's own account can natively see, or the full organization? Ask this as a distinct question from permission mapping — coverage is *which* data is reachable, permissions is *how* access is represented. If full-org coverage requires elevated/admin/compliance access or a different API surface (e.g. an events, audit, export, or compliance endpoint), tell the user that now and let them choose, rather than deferring it. Record the coverage decision and any elevated auth it implies.
   - Is deployment in scope for this connector? If yes, ask for the required deployment target: GCP or AWS, project/account, region, Kubernetes cluster, and container registry. To estimate crawl schedule and resource sizing, ask about expected data volume, how long a full crawl takes or is expected to take, and how fresh the indexed data needs to be. If the user does not know yet, proceed with a reasonable initial estimate, tell them the estimate should be refined after observing an actual full crawl, and record that follow-up. Propose a schedule/resources estimate from the available information and ask the user to confirm or adjust it. Use the default namespace unless the user wants a specific one. If deployment is not in scope, record it as out of scope.
2. Create or identify the connector folder and create its `.glean/` directory.
3. Use the `connector-api-exploration` skill to inspect docs and, when credentials are available, run read-only API probes. Fill `<connector-folder>/.glean/source_investigation.md`, `<connector-folder>/.glean/api_inventory.md`, `<connector-folder>/.glean/api_endpoints.json`, and `<connector-folder>/.glean/api_calls_log.md`.
4. After API exploration is complete, enter planning mode. Draft `<connector-folder>/.glean/connector_plan.md` and ask the user to confirm scope before technical work. This plan is user-facing and must not include internal implementation mechanics such as SDK class names, Python file layout, validation commands, or unit-test commands. Capture:
   - every explored source object and whether it is included in V1, deferred, or excluded
   - the confirmed coverage decision (native-account visibility vs full-org) and the auth/roles it requires
   - every relevant source API endpoint and how it contributes to the selected objects
   - fields available from each endpoint that matter for search, URLs, timestamps, authors, permissions, and metadata
   - the permission/ACL model and, when permissions are non-anonymous, the identity plan: which users (and groups) appear in document ACLs, the source endpoint they are discovered from, and that they will be indexed before documents reference them (streaming connectors do not index identities automatically — see the `connector-push` skill)
   - full-crawl behavior and any incremental follow-up notes
   - test/API-exploration auth and production auth, including when they differ
   - SDK usage mode: full connector flow, push-layer-only, or another confirmed combination
   - Glean-side upload/status endpoints from the `connector-push` skill
   - runtime logging, metrics, and evaluation checks from the `connector-observability` skill
   - expected document count, average document size, freshness needs, source API limits, and recommended crawl frequency
   - deployment/hosting expectations from the `connector-deployment` skill, including whether customer-hosted deployment is in scope
5. Mark the plan as confirmed only after user approval by setting `Status: confirmed`.
6. Revalidate before implementation:

```bash
python scripts/connector_builder/connector_builder.py validate <connector-folder>
```

7. Implement the data client and connector using the `connector-auth`, `connector-pull`, `connector-push`, `connector-observability`, and `connector-deployment` skills as applicable. Post-validation code generation is handled by the agent following the skills, not by the local validator.
8. Evaluate with compile checks and an end-to-end full-crawl smoke run first. Add unit tests only after that path works and the behavior is stable enough for regression coverage.

## Required Artifacts

- `<connector-folder>/.glean/source_docs.json`: confirmed source-of-truth docs.
- `<connector-folder>/.glean/connector_plan.md`: user-confirmed product scope and constraints.
- `<connector-folder>/.glean/source_investigation.md`: auth, source model, sync, permission, and unknowns.
- `<connector-folder>/.glean/api_inventory.md`: cited endpoint catalog and API behavior summary.
- `<connector-folder>/.glean/api_endpoints.json`: structured endpoint list with `name`, `method`, `path`, and `purpose`.
- `<connector-folder>/.glean/api_calls_log.md`: redacted read-only probe log when live API calls are used.
- `<connector-folder>/.glean/connector_plan.md` must include observability choices: provider, lifecycle logs, metrics, and evaluation status/debug checks.
- `<connector-folder>/.glean/connector_plan.md` must include deployment scope: out of scope, customer-hosted GCP/AWS via `glean-deploy`, or follow-up.

## Supporting Skills

- `connector-api-exploration`: source API docs, endpoint inventory, and optional read-only probes.
- `connector-auth`: test/API-exploration auth and production source auth.
- `connector-pull`: source-side full-crawl fetching from confirmed endpoints.
- `connector-push`: Glean-side upload, status, and debug method choices.
- `connector-observability`: logging, metrics, upload visibility, and evaluation checks.
- `connector-deployment`: customer-hosted deployment artifacts and `glean-deploy` operations.
- `connector-testing`: TestHarness validation with full mock, integration/cache, and confirmed E2E modes.

## Evaluation

Evaluate connector quality by checking:

- Planning artifacts are confirmed and internally consistent.
- Generated Python compiles.
- Source fetch returns limited expected records with test credentials, if available.
- Transform/upload paths can push to a test Glean datasource, if credentials are available.
- For permission-trimmed connectors, ACL identities are indexed before documents and a real member passes `check_document_access` — verified end-to-end, not inferred from a successful upload. No `400 ... please index the user before adding permissions` at upload.
- Runtime logs/metrics expose lifecycle, fetch, transform, upload, and failure signals without secrets.
- Deployment artifacts or deployment plan match the confirmed hosting scope, if deployment is in scope.
- After deployment, actual deployed connector logs show lifecycle, fetch, transform, upload, and failure/success signals without secrets.
- Connector behavior matches the confirmed plan, especially full vs incremental crawl constraints.
