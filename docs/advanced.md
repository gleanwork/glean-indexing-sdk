# Advanced Usage

## Choosing a Connector Type

| Connector | Data Client | Best For |
|---|---|---|
| `BaseDatasourceConnector` | `BaseDataClient` | Small-to-medium datasets that fit in memory |
| `BaseStreamingDatasourceConnector` | `BaseStreamingDataClient` | Large datasets with sync/paginated APIs |
| `BaseAsyncStreamingDatasourceConnector` | `BaseAsyncStreamingDataClient` | Large datasets with async APIs (aiohttp, httpx async) |

### BaseDatasourceConnector

**Use when:**

- All data fits comfortably in memory
- Your API returns all data in one call (or a small number of calls)
- You're indexing wikis, knowledge bases, documentation sites, or file systems with moderate content

**Avoid when:**

- The dataset is too large to fit in memory
- Individual documents are very large (> 10MB each)
- Memory usage is a concern

### BaseStreamingDatasourceConnector

**Use when:**

- Data is too large to load all at once
- Your source API is paginated
- You want to process data incrementally to limit memory usage
- You're in a memory-constrained environment

**Avoid when:**

- Your dataset fits comfortably in memory (use `BaseDatasourceConnector` instead for simplicity)

### BaseAsyncStreamingDatasourceConnector

**Use when:**

- Your data source provides async APIs (e.g., `aiohttp`, `httpx` async client)
- You want non-blocking I/O during data retrieval
- You're already working in an async codebase
- You need to make concurrent requests to your source system

**Avoid when:**

- Your source API only has synchronous clients (use `BaseStreamingDatasourceConnector` instead)
- You don't need async I/O benefits

## Forced Restart Uploads

All connector types support forced restart uploads via `force_restart=True`:

```python
connector.index_data(mode=IndexingMode.FULL, force_restart=True)
```

Or for async connectors:

```python
await connector.index_data_async(mode=IndexingMode.FULL, force_restart=True)
```

### When to Use

- Aborting and restarting a failed or interrupted upload
- Ensuring a clean upload state by discarding partial uploads
- Recovering from upload errors or inconsistent states

### How It Works

1. Generates a new `upload_id` to ensure clean separation from previous uploads
2. Sets `forceRestartUpload=True` on the **first batch only**
3. Continues with normal batch processing for subsequent batches

This feature is available on `BaseDatasourceConnector`, `BaseStreamingDatasourceConnector`, `BaseAsyncStreamingDatasourceConnector`, and `BasePeopleConnector`.
