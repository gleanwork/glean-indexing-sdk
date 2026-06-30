---
name: connector-push
description: Implement Glean-side push/upload logic for Glean Indexing SDK connectors. Use when mapping source entities to Glean documents, identities, groups, memberships, and status checks.
---

# Connector Push

Use this skill when implementing the Glean-side upload, validation, and status-check portions of a connector.

## Inputs

- `<connector-folder>/.glean/connector_plan.md`
- `<connector-folder>/.glean/source_investigation.md`
- `<connector-folder>/.glean/api_endpoints.json`
- Source data shapes from the pull/data-client layer.

## Rules

- Use only the SDK push/status wrappers listed below. Do not call undocumented Glean APIs or generated-client methods directly from generated connector code.
- Prefer full-crawl bulk operations for AI-built connectors. Incremental or delete-heavy behavior needs explicit developer attention.
- Record which Glean-side methods are used in `<connector-folder>/.glean/connector_plan.md`.
- Use the load and crawl-frequency decisions from the confirmed connector plan.
- Use local compile/tests first, then test Glean uploads only when indexing credentials are available.

## Allowed SDK Push And Status Surface

Use `PushUploader` from `glean.indexing.push`:

- `configure_datasource`: configures the datasource via the indexing datasource add API.
- `index_documents`: adds or updates a batch of documents (`/api/index/v1/indexdocuments`).
- `bulk_index_documents`: full-crawl document replacement using bulk document upload.
- `bulk_index_single_batch_upload`: uploads one pre-batched bulk document page.
- `delete_document`: deletes one document when explicitly required.
- `index_user`: adds or updates one datasource user.
- `bulk_index_users`: full-crawl datasource user replacement.
- `index_group`: adds or updates one datasource group.
- `bulk_index_groups`: full-crawl datasource group replacement.
- `index_membership`: adds or updates one datasource membership.
- `bulk_index_memberships`: full-crawl datasource membership replacement.
- `delete_user`, `delete_group`, `delete_membership`: delete identity records only when explicitly required.
- `bulk_index_employees`: uploads people/employee records when building a people connector.

Use `StatusClient` from `glean.indexing.push`:

- `get_datasource_status`: checks overall datasource upload/processing status.
- `get_documents_status`: checks upload, indexing, and permission status for specific documents.
- `check_document_access`: checks whether a user has access to a document.

Use these debug helpers only through `PushUploader`:

- `get_document_lifecycle_events`: gets lifecycle events for a datasource document.
- `debug_user`: gets debug information for a datasource user.

Do not use any other Glean-side endpoints in generated connector code.

## Planning Guidance

In `<connector-folder>/.glean/connector_plan.md`, include:

- Source entity to Glean entity mapping.
- Glean object types and document IDs.
- Full-crawl upload choice: `bulk_index_documents`, `bulk_index_users`, `bulk_index_groups`, and/or `bulk_index_memberships`.
- Test upload choice: small `index_documents` or focused bulk upload.
- Status/debug checks to run after upload.
- Auth used for Glean indexing: `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`.
- Production source auth, which may differ from the token used during API exploration.

## Crawl Frequency

Use `<connector-folder>/.glean/connector_plan.md` for expected document count, average document size, freshness requirement, source API limits, hosting owner, and recommended full-crawl frequency. If the plan is missing those decisions, return to the top-level `connector-builder` planning step instead of asking again here.
