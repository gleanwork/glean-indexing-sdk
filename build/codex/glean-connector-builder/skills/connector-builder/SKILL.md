---
name: connector-builder
description: Build Glean Indexing SDK connectors from source-system documentation. Use when planning, generating, validating, or evaluating a custom connector built with the Glean Indexing SDK.
---

# Connector Builder

Use this skill as the top-level workflow for building Glean Indexing SDK connectors with an AI coding agent. It coordinates source documentation confirmation, API exploration, user-confirmed planning, local validation, generation, and evaluation.

## When To Use

Use this skill when the user wants to build, evaluate, or iterate on a connector for a third-party datasource.

## Mental Model

Follow this loop: ask scope -> plan -> run pre-implementation validation -> implement -> test with the `connector-testing` skill after one user confirmation -> deploy if requested -> inspect real deployed logs -> fix and re-run testing if needed.

## Crawl Semantics

A full crawl is complete, self-contained replacement of the indexed state. One successful run must bring Glean to the correct end state on its own: fetch and index every document that currently falls within the confirmed source scope, then use full-crawl stale-document deletion to remove previously indexed documents that are absent from the run. This includes documents deleted at the source and documents that have aged out of a configured coverage window. Pagination and streaming may bound memory usage, but the completed run must still cover the entire confirmed scope. Never finalize a partial or failed fetch as a full crawl, because doing so can delete valid documents as stale.

An incremental crawl processes only changes since a durable checkpoint, including a reliable source-side deletion signal or equivalent reconciliation mechanism. It is an optimization over a correct full-crawl implementation, not the default connector mode. The AI-building workflow supports full crawl only; record incremental crawl as developer-owned follow-up work after full crawl works end-to-end.

## Rules

- Do not generate code until API exploration is complete and the user confirms the connector plan.
- Prefer official source-system docs over prior connector implementations.
- Persist repeated context in the connector folder's `.glean/` directory, not only in the chat. Connector artifacts must live under `<connector-folder>/.glean/`, not a repo-level `.glean/`.
- Do not write connector implementation code until `glean-idx validate` passes.
- Redact secrets from any API call logs.
- The AI-building workflow generates full-crawl connectors only. Do not implement incremental crawl in generated code; record it only as developer follow-up after full crawl works end-to-end.
- Do not add unit tests during initial connector generation. First get a full-crawl connector compiling and passing an end-to-end smoke run; add focused regression tests only after the E2E path is confirmed.
- Always ask the user connector data-model questions before drafting the connector plan. Do not infer final scope from API docs alone.
- Treat every observed difference between test/exploration and the intended production environment as a production-readiness gap, regardless of domain. This includes authentication, scopes, endpoints, data coverage, permissions, rate limits, volume, secret names, runtime configuration, and deployment behavior. A gap may be recorded while development continues, but it is not an optional developer follow-up: implement or configure the production behavior, validate it at the highest feasible fidelity, and update the plan before calling the connector complete or beginning deployment. Reserve developer follow-ups for optional enhancements that are not required by the confirmed production plan.
- Do not ask the user to choose a coverage model until API exploration has established which options are feasible for that source. After exploration, offer only evidence-backed feasible choices; mention infeasible or unverified alternatives separately when useful, but do not present them as selectable options. Explain the required API, roles, scopes, licensing, retention limits, and operational tradeoffs. Recommend organization-wide coverage whenever the source provides a feasible supported path; never present it as available when the research does not support it.
- After making connector or harness implementation changes, you must use the `connector-testing` skill and ask once whether to proceed to the testing step.
- At the start of a connector-building session, check whether this plugin is up to date: compare the locally installed version (`claude plugin list`) against the latest in the open-source repo (the `version` in `package.json` on `main` in `gleanwork/glean-indexing-sdk`). If they differ, tell the user an update is available and give them the exact commands from the README's "Updating the plugin" section (`git pull && npm run build:plugins && claude plugin marketplace update glean-indexing-sdk-agent-plugin && claude plugin update glean-connector-builder@glean-indexing-sdk-agent-plugin`). These commands are for Claude Code; for other AI tools, tell the user the equivalent plugin-update commands for their environment. If the versions match or the check fails, continue without interrupting the user.

## Workflow

1. Ask the pre-exploration questions needed to avoid guessing:
   - Which official source API docs should be used? If the user did not provide docs, search for candidate official docs and ask the user to confirm them once. If no reliable docs can be found, stop and ask for API docs, an OpenAPI spec, or sample API responses.
   - Can the user provide an API base URL and test credentials/token? Recommend this option because live probes materially improve connector quality. Docs-only mode is a fallback, not the preferred path.
   - Which source objects should be considered for indexing and permissions? Ask explicitly about containers, documents/messages/records, comments, files/attachments, users, groups, memberships, and permissions. Treat the answer as exploration scope, not final V1 scope.
   - Is deployment in scope for this connector? If yes, ask for the required deployment target: GCP or AWS, project/account, region, Kubernetes cluster, and container registry. To determine crawl schedule and resource sizing, ask about expected data volume, how long a full crawl takes or is expected to take, and how fresh the indexed data needs to be. Do not propose a schedule without these answers — there is no safe default. If the user does not know yet, ask explicitly, make a conservative first estimate that they must confirm, and record that the schedule should be revisited after the first real crawl completes. Propose a schedule/resources estimate only after the freshness and volume answers are known, and ask the user to confirm or adjust it. Use the default namespace unless the user wants a specific one. If deployment is not in scope, record it as out of scope.
2. Create or identify the connector folder and create its `.glean/` directory.
3. Use the `connector-api-exploration` skill to inspect docs and, when credentials are available, run read-only API probes. Fill `<connector-folder>/.glean/source_investigation.md`, `<connector-folder>/.glean/api_inventory.md`, `<connector-folder>/.glean/api_endpoints.json`, and `<connector-folder>/.glean/api_calls_log.md`.
4. After API exploration, use the cited coverage findings to present the user with the coverage models that are actually feasible for this connector. Explain what content each option can reach and the auth, API, licensing, retention, and operational requirements. Recommend organization-wide coverage when it is feasible. Do not offer unsupported choices merely as generic possibilities. Ask the user to select or confirm the coverage model before drafting the plan.
5. Enter planning mode. Draft `<connector-folder>/.glean/connector_plan.md` and ask the user to confirm scope before technical work. This plan is user-facing and must not include internal implementation mechanics such as SDK class names, Python file layout, validation commands, or unit-test commands. Capture:
   - every explored source object and whether it is included in V1, deferred, or excluded
   - the confirmed coverage model, its user-visible boundary, and the API, roles, scopes, licensing, and retention constraints required to achieve it
   - every relevant source API endpoint and how it contributes to the selected objects
   - fields available from each endpoint that matter for search, URLs, timestamps, authors, permissions, and metadata
   - full-crawl behavior and any incremental follow-up notes
   - test/API-exploration auth and production auth, including when they differ
   - SDK usage mode: full connector flow, push-layer-only, or another confirmed combination
   - Glean-side upload/status endpoints from the `connector-push` skill
   - runtime logging, metrics, and evaluation checks from the `connector-observability` skill
   - expected document count, average document size, freshness needs, source API limits, and recommended crawl frequency
   - deployment/hosting expectations from the `connector-deployment` skill, including whether customer-hosted deployment is in scope
6. Mark the plan as confirmed only after user approval by setting `Status: confirmed`.
7. Revalidate before implementation:

```bash
glean-idx validate <connector-folder>
```

If the SDK is not installed in the current environment, run it without installing:

```bash
uvx --from glean-indexing-sdk glean-idx validate <connector-folder>
```

The command exits `0` when the artifacts are complete and confirmed, and `5` when
they are not, listing every problem it found. Use `--output json` to read the
findings as a list.

8. Implement the data client and connector by reading the required sub-skills **before writing any code for that layer**. Read `connector-pull` before writing the data client. Read `connector-push` before writing document transforms or upload logic. Read `connector-observability` before wiring logging or metrics. Read `connector-auth` if source authentication is non-trivial. Read `connector-deployment` if deployment artifacts are in scope. Do not write implementation code for a layer until its skill has been read. When deployment is in scope, add a module-level zero-argument `create_connector()` factory that builds the configured connector from environment-backed source credentials; keep the connector constructor dependency-injectable for tests. Post-validation code generation is handled by the agent following the skills, not by the local validator.
9. Evaluate with compile checks and an end-to-end full-crawl smoke run. Add unit tests only after that path works and the behavior is stable enough for regression coverage.
10. Before calling the connector complete or starting deployment, re-read the plan and source investigation, compare the tested implementation and configuration with every confirmed production requirement, resolve all test-to-production differences, update the plan with the result, and rerun the relevant validation. Stop and ask for the required decision, credential setup, implementation, or configuration when a production-readiness gap cannot yet be resolved.

## Required Artifacts

- `<connector-folder>/.glean/source_docs.json`: confirmed source-of-truth docs.
- `<connector-folder>/.glean/connector_plan.md`: user-confirmed product scope and constraints.
- `<connector-folder>/.glean/source_investigation.md`: auth, source model, sync, permission, and unknowns.
- `<connector-folder>/.glean/api_inventory.md`: cited endpoint catalog and API behavior summary.
- `<connector-folder>/.glean/api_endpoints.json`: structured endpoint list with `name`, `method`, `path`, and `purpose`.
- `<connector-folder>/.glean/api_calls_log.md`: redacted read-only probe log when live API calls are used.
- `<connector-folder>/.glean/connector_plan.md` must include observability choices: provider, lifecycle logs, metrics, and evaluation status/debug checks.
- `<connector-folder>/.glean/connector_plan.md` must include deployment scope: out of scope, customer-hosted GCP/AWS via `glean-idx deploy`, or follow-up.

## Supporting Skills

- `connector-api-exploration`: source API docs, endpoint inventory, and optional read-only probes.
- `connector-auth`: test/API-exploration auth and production source auth.
- `connector-pull`: source-side full-crawl fetching from confirmed endpoints.
- `connector-push`: Glean-side upload, status, and debug method choices.
- `connector-observability`: logging, metrics, upload visibility, and evaluation checks.
- `connector-deployment`: customer-hosted deployment artifacts and `glean-idx deploy` operations.
- `connector-testing`: TestHarness validation with full mock, integration/cache, and confirmed E2E modes.

## Evaluation

Evaluate connector quality by checking:

- Planning artifacts are confirmed and internally consistent.
- Generated Python compiles.
- Source fetch returns limited expected records with test credentials, if available.
- Transform/upload paths can push to a test Glean datasource, if credentials are available.
- Runtime logs/metrics expose lifecycle, fetch, transform, upload, and failure signals without secrets.
- Deployment artifacts or deployment plan match the confirmed hosting scope, if deployment is in scope.
- After deployment, actual deployed connector logs show lifecycle, fetch, transform, upload, and failure/success signals without secrets.
- Connector behavior matches the confirmed plan, especially full vs incremental crawl constraints.
- No required production behavior remains test-only, unimplemented, unconfigured, unvalidated, or recorded as a developer follow-up.
