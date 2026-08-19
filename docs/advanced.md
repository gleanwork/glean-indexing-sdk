# Advanced Usage

## Choosing a connector type

| Connector | Data client | Use when |
|---|---|---|
| `BaseDatasourceConnector` | `BaseDataClient` | The complete document dataset fits comfortably in memory |
| `BaseStreamingDatasourceConnector` | `BaseStreamingDataClient` | A large or paginated source uses synchronous I/O |
| `BaseAsyncStreamingDatasourceConnector` | `BaseAsyncStreamingDataClient` | A large source provides genuinely asynchronous I/O |
| `BasePeopleConnector` | `BaseDataClient` | Indexing employees rather than documents |

Streaming and incremental indexing solve different problems. Streaming bounds memory while still
supporting a complete full crawl. Incremental indexing limits the source records fetched by passing
a checkpoint through `since`.

For streaming connectors, set `connector.batch_size` to control the maximum number of source
records transformed at once. In-memory document and people connectors fetch and transform the
complete dataset before upload batching:

```python
connector.batch_size = 250
```

## Indexing modes

`IndexingMode.FULL` is a replacement crawl. Previously indexed documents that are absent from a
successfully completed upload are deleted as stale. Never allow an incomplete source fetch to
finish successfully.

`IndexingMode.INCREMENTAL` changes the source fetch by passing a timestamp to the data client:

```python
from glean.indexing.models import IndexingMode

connector.index_data(mode=IndexingMode.FULL)
connector.index_data(mode=IndexingMode.INCREMENTAL)
```

The current connector implementations still use bulk replacement upload APIs after an incremental
fetch. Do not assume that omitted records are protected from stale deletion; use targeted
`PushUploader.index_documents()` calls for deletion-free updates.

The SDK does not persist incremental checkpoints. Override `_get_last_crawl_timestamp()` to read the
last successful checkpoint:

```python
class WikiConnector(BaseDatasourceConnector[WikiPage]):
    def _get_last_crawl_timestamp(self) -> str | None:
        return checkpoint_store.read("company_wiki")
```

Persist the crawl's start time from an external runner only after `index_data()` succeeds:

```python
from datetime import datetime, timezone

started_at = datetime.now(timezone.utc).isoformat()
connector.index_data(mode=IndexingMode.INCREMENTAL)
checkpoint_store.write("company_wiki", started_at)
```

Recording the end time can skip source updates that occur while the crawl is running.

> **Empty full crawls:** An empty source iterator makes no upload call, so it does not delete
> documents from an earlier crawl. However, a non-empty source batch that `transform()` converts to
> an empty document list can still complete an empty upload and trigger stale deletion.

## Connector options

Pass per-run upload behavior through `ConnectorOptions`:

```python
from glean.indexing.models import ConnectorOptions, IndexingMode

options = ConnectorOptions(
    upload_timeout_ms=120_000,
    upload_max_workers=10,
)

connector.index_data(mode=IndexingMode.FULL, options=options)
```

For an async streaming connector:

```python
await connector.index_data_async(mode=IndexingMode.FULL, options=options)
```

### Force restart

`force_restart=True` sends `force_restart_upload=True` on the first document or employee batch. Use
it to recover from an incomplete upload session; do not enable it for every crawl.

```python
connector.index_data(
    mode=IndexingMode.FULL,
    options=ConnectorOptions(force_restart=True),
)
```

### Stale deletion check

Despite its name, `disable_stale_deletion_check=True` forces synchronous stale-data deletion on the
last batch:

```python
connector.index_data(
    mode=IndexingMode.FULL,
    options=ConnectorOptions(disable_stale_deletion_check=True),
)
```

This bypasses the stale-deletion volume safeguard. Use it only when a large deletion is intentional
and the completed crawl scope has been verified.

The generated API uses different parameter names for documents and employee data, while
`ConnectorOptions` exposes one connector-level field. Datasource user, group, and membership
uploads do not currently receive these connector options.

### Upload timeout

`upload_timeout_ms` applies to each bulk upload request. Prefer reducing `connector.batch_size`
before using very large timeouts for oversized payloads.

### Upload concurrency

`upload_max_workers` controls concurrent middle-page document uploads. The first page opens the
upload session and the last page completes it, so both remain sequential. The default is five
workers.

`BasePeopleConnector` does not currently forward `upload_max_workers`; employee batches remain
sequential.

### Document byte limit

`document_batch_size_bytes` is present on `ConnectorOptions`, but the connector base classes do not
currently forward it to `PushUploader`. In-memory document uploads still use the uploader's default
5 MiB limit, while streaming connectors form batches by item count.

To choose a different byte limit today, call `PushUploader.bulk_index_documents()` directly with
`max_batch_bytes`. Connector-level support is tracked in
[issue #106](https://github.com/gleanwork/glean-indexing-sdk/issues/106).

## Identity data with streaming connectors

`BaseDatasourceConnector` runs `get_identities()` before its content crawl. The sync and async
streaming connector implementations override that lifecycle and currently upload only documents.
If streamed documents reference datasource users or groups, index those users, groups, and
memberships separately.

## Further reference

- [Connector types](https://developers.glean.com/libraries/indexing-sdk/concepts/connector-types)
- [Indexing modes](https://developers.glean.com/libraries/indexing-sdk/concepts/indexing-modes)
- [Batching and throughput](https://developers.glean.com/libraries/indexing-sdk/push/batching)
- [PushUploader](https://developers.glean.com/libraries/indexing-sdk/push/uploader)
- [Error handling](https://developers.glean.com/libraries/indexing-sdk/push/error-handling)
