# Status Endpoint Workstream

## Goal

Add a small SDK surface for validating whether data uploaded through the push layer has reached Glean. This should help connector authors answer the first debugging questions after a crawl:

- Did this datasource receive documents, users, groups, and memberships?
- Did the latest bulk upload finish successfully?
- Is a specific document uploaded and indexed?
- Are permissions visible for a specific document?

This is intentionally narrower than wrapping every public debugging endpoint.

## Public API Sources

- Datasource status: <https://developers.glean.com/api-info/indexing/debugging/datasource-status>
- Datasource document debug: <https://developers.glean.com/api-info/indexing/debugging/datasource-document>
- Document lifecycle events: <https://developers.glean.com/api/indexing-api/beta-get-document-lifecycle-events>
- Deprecated document status: <https://developers.glean.com/api/indexing-api/get-document-upload-and-indexing-status>
- Deprecated document count: <https://developers.glean.com/api/indexing-api/get-document-count>

The public docs point users toward the `/debug/{datasource}/...` endpoints. The older `/getdocumentstatus` and `/getdocumentcount` endpoints are deprecated with removal scheduled for 2026-10-15, so the SDK should not add new first-class wrappers for them.

## Proposed SDK Surface

Introduce a read-only status helper in the existing push uploader module:

```python
from glean.indexing.push import StatusClient

status = StatusClient(datasource="gleantest")
datasource_status = status.get_datasource_status()
document_status = status.get_document_status(object_type="Article", document_id="art123")
```

Keep this separate from `PushUploader`. Uploading and debugging are related workflows, but mixing readback calls into the uploader would make the push layer look like it guarantees indexing completion. The status endpoints are explicitly debugging and validation APIs.

### P0: Datasource Status

Support `POST /api/index/v1/debug/{datasource}/status` via the generated client method `client.indexing.datasource.status`.

The wrapper should return the generated response model directly in the first version. Avoid reshaping the beta response into SDK-owned models until the API stabilizes. The documented response includes:

- document bulk upload history
- uploaded and indexed document counts by object type
- document processing history
- identity processing history
- users, groups, and memberships upload counts

This gives the SDK enough signal for post-crawl validation without recreating the Glean admin/debug UI.

### P0: Document Debug Status

Support `POST /api/index/v1/debug/{datasource}/document` via the generated client method `client.indexing.documents.debug`, taking:

- `object_type`
- `document_id`

Map `document_id` to the generated method's `doc_id` argument. Return the generated response model directly. The documented response contains upload status, index status, upload/index timestamps, and effective document permissions.

This should be the main replacement for deprecated `getdocumentstatus` support.

### P1: Convenience Assertions For Tests

Add optional test helper methods on `MockGleanClient` only after the status wrapper exists:

- Assert that datasource status was requested for a datasource.
- Assert that document debug status was requested for an object type and document id.

These should mirror the existing raw generated-client assertions used by `PushUploader` tests rather than inventing a fake status simulator.

### P1: Documentation Recipes

Add a short "Validate an upload" example to `docs/advanced.md` or a dedicated debugging page:

1. Run a connector upload.
2. Call `StatusClient.get_datasource_status()`.
3. Check the latest bulk upload history and uploaded/indexed counts.
4. Call `StatusClient.get_document_status()` for one representative document when counts are off or permissions look wrong.

Be explicit that these endpoints are for validation/debugging, not a scheduling or blocking wait primitive.

## Non-Goals

- Do not support deprecated `/api/index/v1/getdocumentstatus`.
- Do not support deprecated `/api/index/v1/getdocumentcount`.
- Do not add a polling/wait-until-indexed abstraction in the first pass.
- Do not parse the datasource status response into SDK-owned dataclasses yet.
- Do not wrap every troubleshooting endpoint.
- Do not include document lifecycle events in P0. The public lifecycle endpoint is beta, rate limited to one request per minute per datasource, and more detailed than the immediate SDK need.

## Implementation Shape

Add a `StatusClient` class to `src/glean/indexing/push/uploader.py` that follows the existing `PushUploader` constructor style:

- `datasource`
- `retries`
- `server_url`
- `timeout_ms`
- `http_headers`

Reuse the same request-option forwarding pattern used by `PushUploader` so generated-client behavior remains consistent across SDK helper layers.

Export the helper from:

- `src/glean/indexing/push/__init__.py`
- `src/glean/indexing/__init__.py`

Because `StatusClient` lives in `uploader.py`, the existing `src/glean/indexing/testing/_patch_targets.py` entry for `glean.indexing.push.uploader.api_client` also covers status calls.

## Test Plan

Unit tests should cover:

- `get_datasource_status()` calls the generated troubleshooting client with the datasource and forwarded request options.
- `get_document_status()` builds the generated debug document request with datasource, object type, and document id.
- `StatusClient` is exported from `glean.indexing.push` and top-level `glean.indexing`.
- `mock_glean_client()` patches status client calls through the same mock facade.

If the installed generated client has a different namespace or method name than the public snippets show, adapt the wrapper to the generated surface and keep the public SDK method names stable.

## Open Questions

- Should the helper be named `StatusClient`, `TroubleshootingClient`, or `DebugClient`? `StatusClient` is friendliest for connector authors, but `TroubleshootingClient` matches the generated client naming.
- Should `PushUploader` expose a `status()` convenience factory returning `StatusClient(datasource=self.datasource, ...)`, or should users instantiate the status helper explicitly?
- Should lifecycle events become P2 once the beta endpoint stabilizes or when connector authors need per-document event history beyond current upload/index status?
