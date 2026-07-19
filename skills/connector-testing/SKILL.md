---
name: connector-testing
description: Validate the Glean Indexing SDK TestHarness implementation with the existing pytest suite. Use when checking the full mock, integration/cache, or end-to-end harness structure, and after an agent changes harness implementation code.
---

# Connector Testing

Use this skill to validate the SDK testing harness introduced under `glean.indexing.testing.harness`.

## Rules

- Before running validations, ask for confirmation once for the whole testing step. Include every command that will run in that single prompt; do not ask again for each command in the same validation batch.
- In the same testing-step prompt, say which validation levels will run. Use the existing task context, including the connector-local `.env` file if already identified, to determine whether required Glean and connector source tokens are present. If token presence is missing or unknown, say that E2E testing is recommended but will not happen unless the required tokens are present.
- If you make any code changes after a test run, ask the user whether to run the harness validation again.
- Never print secrets, commit `.env`, or include recorded source data.
- Run the offline config-consistency checks below in the full-mock level (no credentials needed) BEFORE any live upload. These catch upload-time `400` rejections (e.g. undeclared object types) without spending a real API round-trip.

## Offline Config-Consistency Checks (full-mock, run first)

These run against a full-mock crawl (`run_connector` -> `MockGleanClient`) and require no credentials. They catch the mismatches the Glean indexing API only reports as a `400` at live upload time:

- **Object types are declared.** Every distinct `object_type` on `client.documents_posted` must appear as a `name` in the connector's `configuration.object_definitions`. An object type set on a document but not declared in the config is rejected at upload with `400 ... Object definitions not found for object types: <Name>`. Assert this offline, e.g.:

  ```python
  client = run_connector(connector)
  declared = {o.name for o in (connector.configuration.object_definitions or [])}
  used = {d.object_type for d in client.documents_posted if d.object_type}
  assert used <= declared, f"Undeclared object types: {used - declared}"
  ```

- **Datasource is configured before upload.** Use `client.assert_datasource_configured()`.
- **Documents carry required fields.** Non-empty `id`, `datasource` matching the connector name, and (for permissioned sources) non-empty `permissions` so nothing is unintentionally world-visible.

If any offline check fails, fix the connector and re-run before attempting a live upload.

## Validation Levels

The existing harness pytest suite validates all three harness levels:

1. Full mock: source side mocked, Glean side mocked.
   - Covered by `tests/unit_tests/testing/harness/test_harness_phase1.py`.

2. Integration: source side real or recorded, Glean side mocked.
   - Covered by `tests/unit_tests/testing/harness/test_harness_phase2.py`.
   - Cache, recording, replay, config, and negative identity behavior are covered by the harness subdirectory.

3. End-to-end: source side real, Glean side real.
   - Interface and wiring are covered by `tests/unit_tests/testing/harness/test_harness_phase3.py`.
   - A live E2E run requires Glean credentials and a test instance; do not assume it is included in the unit suite.

## Credential Context

Live E2E validation requires Glean credentials (`GLEAN_INDEXING_API_TOKEN` and `GLEAN_SERVER_URL` or `GLEAN_INSTANCE`) plus any connector-specific source tokens required by the connector. These are usually in the connector-local `.env` file copied from `.env.example`.

Use the existing task context to determine whether required tokens are present. If the tokens are missing, or if their presence is unknown, tell the user that live E2E testing is recommended but will not happen unless the required Glean and connector tokens are present. The existing pytest harness suite can still validate the full mock, integration/cache, and E2E interface structure.

## Live E2E Verification (after a real upload, credentials required)

A successful upload does not prove documents are searchable. For a permissioned datasource, indexing and access succeed independently, so verify both:

By default, do NOT configure the datasource with `isTestDatasource=true` (`is_test`). A Glean test datasource restricts document visibility to designated test users, which makes `check_document_access` return `false` for ordinary users and defeats permission verification. Use a normal datasource for test runs — a distinct name (e.g. `<name>2`) is fine for an isolated clean-room test. Only set `isTestDatasource` if you explicitly want that isolation and are not relying on access checks.

1. **Indexed, not just uploaded.** `StatusClient.get_datasource_status` -> `documents.counts.indexed` is non-zero for each object type (not only `uploaded`). Per document: `StatusClient.get_documents_status([...])` -> each `indexingStatus: INDEXED`.
2. **Permissions uploaded.** On `get_documents_status`, `permissionIdentityStatus` is an enum of `NOT_UPLOADED`, `UPLOADED`, `STATUS_UNKNOWN`. `UPLOADED` is the healthy value; there is no "processed" state to wait for. `NOT_UPLOADED` means the document's permissions were not uploaded and visibility is affected — that is the failure to catch.
3. **Access resolves both ways (positive and negative).** Verify permission trimming in both directions with `check_document_access(object_type, document_id, user_email)`:
   - **Positive:** a user who IS in a document's source ACL returns `hasAccess: true`.
   - **Negative:** a user who is NOT in that document's ACL returns `hasAccess: false`.
   The negative check is essential — it proves the connector is not over-sharing (world-readable, wrong ACLs, or leaking across containers). A green positive check alone does not catch over-permissioning.

You do not need a full crawl to verify permissions. Pushing a **small sample of documents** is enough, as long as the sample includes at least one restricted document plus a user who should see it and a user who should not. Prefer this focused sample for permission verification.

Trigger processing once after the test push. Uploaded documents are otherwise processed on a periodic (sometimes ~daily) cycle, so a fresh test upload may not be indexed for a long time. After pushing the test docs, call `/processalldocuments` **once** for the test datasource (`client.indexing.documents.process_all(request=ProcessAllDocumentsRequest(datasource=<name>))`) to schedule immediate processing. This endpoint is **heavily rate-limited** — call it a single time per test run and do not retry it soon; then poll the status/access checks below rather than calling `process_all` again. Use `get_document_lifecycle_events` (also rate-limited, ~1/min) to see a document's `UPLOADED`/`INDEXED` timeline and confirm processing actually ran.

Notes:

- Non-anonymous permissions require the referenced users to be **indexed** (e.g. via `get_identities()` / `bulk_index_users`), even when referencing by email. A document can be `INDEXED` with `permissionIdentityStatus: UPLOADED` and still return `hasAccess: false` if its ACL users were never indexed. Confirm the connector indexes the users it references.
- Both indexing and permissions are **asynchronous**, so verify by **polling**, not a single check. Upload completes immediately, but a document's `indexingStatus` can stay `NOT_INDEXED` and `check_document_access` can stay `false` for minutes after upload. Poll `get_documents_status` + `check_document_access` on a short interval (e.g. every ~2 minutes) until access is granted or a timeout (e.g. ~30 minutes) is reached. Check upload/index recency too: `lastUploadedAt` should reflect the current run, and `lastIndexedAt` should advance past the upload time before you trust a `false` access result — a `false` while the doc has not been re-indexed since upload is inconclusive, not a failure.
- Poll a **deterministically chosen single document** (or a tiny fixed sample), not an arbitrary number of documents. Choose one restricted document whose ACL includes a target user (for the positive check) and excludes another (for the negative check), and state why that document was chosen. Do not poll "all of a user's documents" or an arbitrary count — that is not a methodology and wastes API calls. Verifying permission trimming correctly on one representative restricted document is sufficient; scale up only with a stated reason.
- `permissionIdentityStatus` enum is `NOT_UPLOADED` / `UPLOADED` / `STATUS_UNKNOWN`; `UPLOADED` is healthy and `NOT_UPLOADED` means the document's permissions were not uploaded. It does not indicate whether ACL users were indexed — `check_document_access` is the end-to-end signal.
- If access stays `false` after the docs are freshly indexed and the users are indexed, confirm the ACL email matches the user's Glean identity (same email); on a test instance the user may simply not be provisioned in Glean.

## Test-Run Report

When a live test crawl is run, produce a short human-readable run report and point the end developer to it so they can manually verify. Save it under the connector's `.glean/` (e.g. `.glean/run_report.md`) and tell the developer to open it for details. The report should reconcile what was pulled against what was pushed:

- **Pulled from source:** counts of records/documents, containers, and distinct users; the time range covered; and a per-container breakdown when useful.
- **Pushed to Glean:** datasource name, number of datasource users indexed, number of documents indexed, and object types used.
- **Identities indexed:** the list of datasource users pushed (`bulkindexusers`), since document ACLs only grant access to indexed users.
- **Permissions pushed (document -> allowed users):** for a permissioned datasource, list each document's ACL (`permissions.allowedUsers`) so the developer can see exactly which users each document was shared with.
- **Per-user visibility:** an inverted view of the ACLs — for each user, how many documents they can see (and a few sample titles) — so the developer can sanity-check that permission trimming matches the source.
- **Glean-reported status:** `get_datasource_status` `uploaded` vs `indexed` counts per object type, and the latest upload's `status` / `processingState`. Note that these are datasource-wide cumulative totals, not per-run; if per-run deltas are needed, snapshot counts before and after the run.
- **Sample documents:** a handful with their IDs, titles, view URLs, and ACL sizes, so the developer can eyeball them.
- **How to check manually:** confirm the datasource is enabled in the admin console; search a distinctive phrase as a user who is a member/has access; and note that permissions process asynchronously so access may lag the upload.

Explicitly ask the end developer to review the report and cross-check it in Glean, rather than treating a green run as sufficient on its own.

## Existing Harness Suite
For normal harness validation, ask before running:

```bash
uv run pytest tests/unit_tests/testing/harness -v
```

If public testing exports or shared testing utilities changed, ask before widening to:

```bash
uv run pytest tests/unit_tests/testing -v
```
