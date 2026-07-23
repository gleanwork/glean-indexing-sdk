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
   - After uploading documents, the harness waits for normal indexing, requests `processalldocuments` once when needed, ignores a rate-limit response from that request, and polls document status for a bounded period. If the result is `PENDING`, tell the user: "Source data was pulled successfully, and Glean accepted the document upload without validation errors. The documents are queued for asynchronous indexing, which may take longer." Then determine the next step from the confirmed connector plan and ask whether they want to proceed. Do not treat pending asynchronous indexing as a connector failure or generate connector-specific processing code.

## Credential Context

Live E2E validation requires Glean credentials (`GLEAN_INDEXING_API_TOKEN` and `GLEAN_SERVER_URL` or `GLEAN_INSTANCE`) plus any connector-specific source tokens required by the connector. These are usually in the connector-local `.env` file copied from `.env.example`.

Use the existing task context to determine whether required tokens are present. If the tokens are missing, or if their presence is unknown, tell the user that live E2E testing is recommended but will not happen unless the required Glean and connector tokens are present. The existing pytest harness suite can still validate the full mock, integration/cache, and E2E interface structure.

## Existing Harness Suite

For normal harness validation, ask before running:

```bash
uv run pytest tests/unit_tests/testing/harness -v
```

If public testing exports or shared testing utilities changed, ask before widening to:

```bash
uv run pytest tests/unit_tests/testing -v
```
