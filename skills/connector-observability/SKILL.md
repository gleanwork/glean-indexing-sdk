---
name: connector-observability
description: Plan and implement logging, metrics, and evaluation visibility for Glean Indexing SDK connectors. Use when wiring connector runtime observability or deciding what to verify after a connector run.
---

# Connector Observability

Use this skill when adding runtime visibility to an AI-built connector or when planning the eval/reporting portion of a connector build.

## Inputs

- `<connector-folder>/.glean/connector_plan.md`
- `<connector-folder>/.glean/source_investigation.md`
- `<connector-folder>/.glean/api_endpoints.json`
- The generated connector/data-client files

## Rules

- Use SDK observability APIs only. Do not invent logging/metrics helpers.
- Keep logs structured and secret-free.
- Never log raw source API tokens, Glean indexing tokens, cookies, or request bodies that may contain customer content.
- Prefer connector-level lifecycle, fetch, transform, upload, status, and failure visibility over noisy per-record logs.
- Record the observability plan in `<connector-folder>/.glean/connector_plan.md` before implementation.

## SDK Observability Surface

Use these exports from `glean.indexing.observability`:

- `ConnectorObservability`: central runtime object for common fields, lifecycle logs, phase logs, upload logs, and metrics.
- `setup_connector_logging`: configures structured logging for a connector logger.
- `StructuredFormatter` and `CompactStructuredFormatter`: structured console/log formatting.
- `ConsoleLoggerProvider`: default local logging provider.
- `MetricsProvider` and `MetricType`: custom metrics backend interface.
- `NoOpMetricsProvider`: default no-op metrics provider.
- `InMemoryMetricsProvider`: test/development metrics provider.
- `with_observability`: decorator for method-level observability when appropriate.
- `track_crawl_progress`: decorator/helper for crawl progress logging when appropriate.
- `PerformanceTracker`: timing helper for local performance tracking.

If the connector uses `PushUploader`, pass a `ConnectorObservability` instance through its `observability` parameter so upload/batch events are logged and metrics are emitted by the SDK wrapper.

## What To Instrument

Plan and implement visibility for:

- Crawl lifecycle: started, completed, failed.
- Source fetch: started, completed, item count, duration, source endpoint or entity type.
- Transform: input count, output count, duration, filtered/skipped count when known.
- Upload: batch start, batch completion, batch failure, batch size, upload ID.
- API behavior: request count, latency, retry count, error count when available through SDK methods.
- Evaluation: status checks run after upload and their results.

## Glean Status And Debug Checks

Use `connector-push` for the allowed status/debug surface. The observability plan should say which of these will run after a test upload:

- `StatusClient.get_datasource_status`
- `StatusClient.get_documents_status`
- `StatusClient.check_document_access`
- `PushUploader.get_document_lifecycle_events`
- `PushUploader.debug_user`

Do not call undocumented status or debug endpoints directly.

## Required Plan Fields

Before implementation, ensure `<connector-folder>/.glean/connector_plan.md` includes:

- Observability provider choice: console/no-op/in-memory/custom.
- Lifecycle events to log.
- Source fetch and transform counts to report.
- Upload metrics and batch events to report.
- Status/debug checks to run during evaluation.
- Secret-redaction expectations.

## Local Evaluation Guidance

For a credential-free planning eval, the plan should describe the observability that will be wired later. Do not require live metrics backends.

For an implementation eval with credentials, verify:

- Generated Python compiles.
- Connector run emits lifecycle/fetch/transform/upload logs.
- Upload status/debug checks are attempted only when Glean indexing credentials are available.
- No secret values appear in logs or `.glean/` artifacts.
