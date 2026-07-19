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
- Use full-crawl bulk operations for AI-built connectors. Incremental, partial-update, or delete-heavy behavior needs explicit developer attention after full crawl works.
- Every custom `object_type` set on a `DocumentDefinition` MUST have a matching entry in the datasource's `configuration.object_definitions` (each with a `name` equal to the `object_type`). Otherwise the indexing API rejects the whole batch at upload time with `400 ... Object definitions not found for object types: <Name>`. If you do not declare object definitions, do not set `object_type` on documents either. Keep the two in sync as a pair.
- Record which Glean-side methods are used in `<connector-folder>/.glean/connector_plan.md`.
- Use the load and crawl-frequency decisions from the confirmed connector plan.
- Use compile checks and an end-to-end full-crawl smoke run first. Add unit tests only after the connector behavior is confirmed and worth regression testing.
- A successful upload response (HTTP 200 / "batch upload completed") only means Glean **accepted** the batch. It is NOT proof that documents were indexed. Confirm indexing with `StatusClient.get_datasource_status` and check that the `indexed` counts for your object type are non-zero, not just the `uploaded` counts (see `connector-observability`).

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

### Permission identities and access

Non-anonymous document permissions only grant access after the referenced users are **indexed** — this is required even when referencing users by email. Uploading a document whose ACL lists a user does not by itself let that user find it; Glean must separately know the user exists. See https://developers.glean.com/api-info/indexing/documents/permissions ("users need to be indexed before being referenced").

- **Index the ACL users.** Every user referenced in a document's `allowed_users` must be indexed, e.g. by returning them from the connector's `get_identities()` (the base datasource connector uploads identities before documents) or via `bulk_index_users`. Indexing a user only tells Glean the user exists; it does not by itself grant document access.
- **`is_user_referenced_by_email=True`:** reference users by `email` in `allowed_users`, and index those same users by email. If `false`, reference and index by `datasourceUserId`.
- **Processing is asynchronous.** Permissions and memberships are processed after upload, so `check_document_access` can be `false` for a short delay, then become `true`.
- **`permissionIdentityStatus`** from `get_documents_status` is an enum of `NOT_UPLOADED`, `UPLOADED`, `STATUS_UNKNOWN` (always `STATUS_UNKNOWN` when the datasource sets `identityDatasourceName`). `UPLOADED` is the healthy value for a document's permissions; `NOT_UPLOADED` means the document's permissions were not uploaded and visibility is affected. It does NOT reflect whether the referenced users were indexed — verify end-to-end access with `check_document_access`.
- **Group-based permissions** additionally require indexing groups and memberships (`bulk_index_groups` / `bulk_index_memberships`), then `client.indexing.permissions.process_memberships`.

Use these debug helpers only through `PushUploader`:

- `get_document_lifecycle_events`: gets lifecycle events for a datasource document.
- `debug_user`: gets debug information for a datasource user.

Do not use any other Glean-side endpoints in generated connector code.

## Planning Guidance

In `<connector-folder>/.glean/connector_plan.md`, include:

- Source entity to Glean entity mapping.
- Glean object types and document IDs. For every object type, list the matching `configuration.object_definitions` entry that declares it (object type set on documents but not declared in the config is the most common cause of a 400 at upload).
- Identity plan for permissions: which users appear in document ACLs and how they are indexed (`get_identities()` / `bulk_index_users`), since non-anonymous permissions require those users to be indexed before they grant access. Add groups/memberships only for group-based permissions.
- Full-crawl upload choice: `bulk_index_documents`, `bulk_index_users`, `bulk_index_groups`, and/or `bulk_index_memberships`.
- Test upload choice: small `index_documents` or focused bulk upload.
- Status/debug checks to run after upload, including a `get_datasource_status` check that `indexed` counts (not just `uploaded`) are non-zero for each object type, and a `check_document_access` check that a real member can actually see a document.
- Auth used for Glean indexing: `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`.
- Production source auth, which may differ from the token used during API exploration.

## Crawl Frequency

Use `<connector-folder>/.glean/connector_plan.md` for expected document count, average document size, freshness requirement, source API limits, hosting owner, and recommended full-crawl frequency. If the plan is missing those decisions, return to the top-level `connector-builder` planning step instead of asking again here.
