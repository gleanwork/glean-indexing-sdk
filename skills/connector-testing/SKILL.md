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

## Existing Harness Suite

For normal harness validation, ask before running:

```bash
uv run pytest tests/unit_tests/testing/harness -v
```

If public testing exports or shared testing utilities changed, ask before widening to:

```bash
uv run pytest tests/unit_tests/testing -v
```
