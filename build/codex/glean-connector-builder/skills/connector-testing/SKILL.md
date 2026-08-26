---
name: connector-testing
description: Test a generated connector through full-mock, integration/cache, and live end-to-end phases using the public utilities under glean.indexing.testing.
---

# Connector Testing

Use this skill after implementing or changing a connector. Exercise the connector with the public SDK testing layer under `src/glean/indexing/testing/`; do not test the SDK testing layer itself.

## Rules

- Never run files under the repository's `tests/` directory while using this skill. Those tests validate the SDK implementation and belong to SDK-maintainer CI, not the connector-building workflow.
- Use only public utilities exported by `glean.indexing.testing`, including `TestHarness`, `TestConfig`, static data clients, `MockGleanClient`, and `run_connector`.
- Before validation, ask for confirmation once for the whole testing step and state which phases will run. Do not ask again for each phase in the same batch.
- Before the live end-to-end phase specifically, state the resolved `GLEAN_SERVER_URL` / `GLEAN_INSTANCE` target and confirm with the user before proceeding -- this phase uploads real documents with no automated cleanup. Only call `run_end_to_end(confirm=True)` / `run_end_to_end_async(confirm=True)` after that confirmation.
- Use the existing task context, including the connector-local `.env` file if identified, to determine whether source and Glean credentials are present.
- If connector code changes after a run, ask whether to run the connector validation again.
- Never print secrets, commit `.env`, or include recorded source data.
- Ensure test data includes at least one representative document for every type the connector can emit across mock, integration, and live end-to-end validation when available.

## Public Testing Layer

Use these SDK files and their public exports:

- `src/glean/indexing/testing/harness/harness.py`: `TestHarness`
- `src/glean/indexing/testing/harness/config.py`: `TestConfig`, `ClientConfig`
- `src/glean/indexing/testing/data_clients.py`: static sync, streaming, and async clients
- `src/glean/indexing/testing/mock_client.py`: `MockGleanClient`
- `src/glean/indexing/testing/runner.py`: `run_connector`, `run_connector_async`
- `src/glean/indexing/testing/harness/cache/`: source recording and replay
- `src/glean/indexing/testing/harness/permissions.py`: permission-payload assertions
- `src/glean/indexing/testing/validation.py`: deterministic connector-output validation
- `src/glean/indexing/push/status.py`: shared one-shot and polling status checks

## Connector Validation Phases

Each phase is available from the CLI as well as from Python. Use the CLI when you
just need the phase run and reported; use the harness directly when you need to
assert on the returned client.

```bash
glean-idx test --phase mock          # or integration, live
glean-idx test --phase all           # every phase in order
```

`--phase all` stops at the first failure and skips any phase that cannot run,
reporting which. `--max-items N` caps what each data client yields.

### 1. Full mock

Use static test data representative of every connector output type. Run:

```bash
glean-idx test --phase mock
```

or, to assert on the result:

```python
harness.run_full_mock()
```

This phase must not call the source or Glean. Inspect the returned `MockGleanClient` for emitted documents, users, groups, memberships, and employees. Deterministic output validation runs automatically.

### 2. Integration/cache

Register the connector's real source clients in `TestHarness.clients`, keep Glean mocked, and run:

```bash
glean-idx test --phase integration   # add --refresh-cache to re-record
```

or, to assert on the result:

```python
harness.run_integration_test()
```

The CLI discovers the connector's data clients by type, so `TestHarness.clients`
does not have to be spelled out when running it that way.

This phase fetches a bounded source sample on a cache miss and records it locally; later runs replay the cache. Verify source parsing, transformation, document counts, and permission payloads without calling Glean.

Use `run_integration_test_async()` for async streaming connectors.

### 3. Live end-to-end

> **Production safety:** this phase uploads real documents to whichever Glean
> instance `GLEAN_SERVER_URL` (or `GLEAN_INSTANCE`) resolves to, and there is
> **no automated cleanup**. Before running it, state the resolved target and
> confirm with the user before proceeding. See **Cleaning up after a live
> run** below for how to remove what it uploads.

Run only when source credentials and `GLEAN_INDEXING_API_TOKEN` plus `GLEAN_SERVER_URL` or `GLEAN_INSTANCE` are available:

```bash
glean-idx test --phase live
```

This prompts for confirmation (showing the resolved target) unless `--yes` is passed.

or, to assert on the result:

```python
harness.run_end_to_end(confirm=True)
```

`run_end_to_end()` / `run_end_to_end_async()` refuse to run and raise `LiveEndToEndNotConfirmedError` unless called with `confirm=True` -- pass it only after verifying the target with the user. Use `run_end_to_end_async()` for async streaming connectors. This phase uses the current bounded source client and real Glean APIs; it never reads or writes integration fixtures.

After upload, the harness waits for normal indexing, requests `processalldocuments` once when needed, ignores a rate-limit response from that request, and polls status for a bounded period. If the result is `PENDING`, tell the user:

> Source data was pulled successfully, and Glean accepted the document upload without validation errors. The documents are queued for asynchronous indexing, which may take longer.

Then determine the next step from the confirmed connector plan and ask whether they want to proceed. Do not treat pending asynchronous indexing as connector failure or generate connector-specific processing code.

If live credentials are unavailable, explicitly report that the live phase was skipped. Full-mock and integration results do not prove that Glean accepted or indexed the documents.

## Document Indexing Status

For checking document status during testing, use `glean-idx document status --datasource <datasource> --document <object-type> <document-id> --poll`; omit `--poll` for an ad-hoc single check. Repeat `--document <object-type> <document-id>` to check multiple documents.

When a document uploaded but never became searchable, `glean-idx document events --datasource <datasource> --object-type <type> --id <id>` shows its lifecycle, and `glean-idx datasource status --datasource <datasource>` compares uploaded against indexed counts.

## Cleaning up after a live run

A live end-to-end run has no automated cleanup. On success, the harness logs a `glean-idx document delete --datasource <name> --document <object-type> <id> ...` command naming every document it just uploaded -- run that command (or `PushUploader.delete_document(...)` from Python) to remove them. Do this whenever the live phase ran against anything other than a disposable test datasource.

## Run Report

After the selected phases finish, report:

- phases run and skipped
- source records fetched or replayed
- documents and identities emitted
- object types represented
- deterministic validation results
- live upload and indexing result, when E2E ran
- any remaining production-readiness gaps
