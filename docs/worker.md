# Worker

The worker is a subprocess that discovers and executes Glean indexing connectors inside a project's virtual environment. It communicates with its parent process via [JSON-RPC 2.0](https://www.jsonrpc.org/specification) over stdin/stdout, following patterns similar to the Language Server Protocol (LSP).

## Ecosystem

The worker is one piece of a larger toolchain for building Glean connectors:

| Component | Purpose |
|---|---|
| **glean-indexing-sdk** (this repo) | SDK base classes and the worker subprocess |
| **Copier template** | Scaffolds a new connector project with the SDK as a dependency |
| **Glean MCP server** | Spawns the worker to let AI agents create, edit, and run connector projects |
| **Claude plugin** | Wraps the MCP server for use with Claude |

The MCP server is the primary consumer of the worker. It spawns the worker inside a connector project's virtual environment, sends JSON-RPC requests to discover connectors and execute them, and surfaces the worker's notifications (progress, errors, field mappings) back to the AI agent.

## Running the Worker

The worker is invoked as a Python module inside a connector project:

```bash
cd /path/to/connector/project
uv run python -m glean.indexing.worker
```

Or with an explicit project path:

```bash
uv run python -m glean.indexing.worker --project /path/to/project
```

The worker reads JSON-RPC requests from stdin and writes responses/notifications to stdout. Logs go to stderr.

If a `.env` file exists in the project directory, it is loaded automatically (requires `python-dotenv`).

## Lifecycle

1. **Startup** — The parent process spawns the worker. The worker begins reading from stdin.
2. **Initialize** — The parent sends an `initialize` request. The worker discovers the project and its connectors.
3. **Discover** — The parent can send `discover` to re-scan for connectors at any time.
4. **Execute** — The parent sends `execute` with a connector name. The worker runs the connector through fetch → transform → upload phases, emitting notifications for each record.
5. **Control** — During execution, the parent can `pause`, `resume`, `step`, or `abort`.
6. **Shutdown** — The parent sends `shutdown` or closes stdin. The worker exits gracefully.

The worker also exits if its parent process dies (detected via PID watchdog on Unix).

## JSON-RPC Protocol

### Requests

All requests follow JSON-RPC 2.0 format: `{"jsonrpc": "2.0", "id": 1, "method": "...", "params": {...}}`.

#### `initialize`

Discovers the project and returns metadata plus all found connectors.

**Params:** none

**Response:**
```json
{
  "server_version": "0.1.0",
  "project": {
    "path": "/path/to/project",
    "name": "my-connector",
    "python_version": "3.12.0",
    "has_pyproject": true,
    "has_mock_data": true,
    "mock_data_path": "/path/to/project/mock_data.json"
  },
  "connectors": [
    {
      "class_name": "MyConnector",
      "module_path": "src.my_connector",
      "file_path": "/path/to/project/src/my_connector.py",
      "source_type": "MyDataType",
      "base_classes": ["BaseDatasourceConnector"],
      "methods": ["transform"],
      "category": "connector",
      "data_clients": ["MyDataClient"],
      "configuration": {
        "name": "my_datasource",
        "display_name": "My Datasource"
      }
    }
  ],
  "capabilities": ["execute", "pause", "resume", "step", "abort"]
}
```

#### `discover`

Re-scans the project for connector classes. Useful after the user modifies code.

**Params:** none

**Response:**
```json
{
  "connectors": [...]
}
```

#### `execute`

Starts executing a connector. Returns immediately; progress is reported via notifications.

**Params:**
| Field | Type | Description |
|---|---|---|
| `connector` | `string` | Class name of the connector to execute (required) |
| `step_mode` | `bool` | If `true`, pause after each record and wait for `step` requests (default: `false`) |
| `mock_data_path` | `string \| null` | Path to mock data JSON file. If omitted, the worker checks for `mock_data.json` / `test_data.json` in the project root, then falls back to the real data client. |

**Response:**
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started"
}
```

#### `pause` / `resume` / `step` / `abort`

Control a running execution.

**Params:** none

**Response:** `{"status": "paused" | "resumed" | "stepped" | "aborted"}`

#### `shutdown`

Tells the worker to exit gracefully.

**Params:** none

**Response:** `{"status": "shutting_down"}`

### Notifications

Notifications are JSON-RPC messages without an `id` — the parent does not respond to them. The worker emits these during execution to report progress.

#### `phase_start`

Emitted when a phase begins.

```json
{"jsonrpc": "2.0", "method": "phase_start", "params": {"phase": "get_data", "total_records": 42}}
```

Phases: `get_data`, `transform`, `post_to_index`.

#### `phase_complete`

Emitted when a phase finishes.

```json
{"jsonrpc": "2.0", "method": "phase_complete", "params": {
  "phase": "transform",
  "records_processed": 42,
  "duration_ms": 1234.5,
  "success": true
}}
```

#### `record_fetched`

Emitted for each record retrieved during the `get_data` phase.

```json
{"jsonrpc": "2.0", "method": "record_fetched", "params": {
  "record_id": "page_123",
  "index": 0,
  "data": {"id": "page_123", "title": "...", "content": "..."}
}}
```

#### `transform_complete`

Emitted for each record successfully transformed.

```json
{"jsonrpc": "2.0", "method": "transform_complete", "params": {
  "record_id": "page_123",
  "index": 0,
  "input_data": {"id": "page_123", "title": "..."},
  "output_data": {"id": "page_123", "title": "...", "datasource": "..."},
  "field_mappings": [
    {"source_field": "title", "target_field": "title"},
    {"source_field": "content", "target_field": "body"}
  ],
  "duration_ms": 2.3
}}
```

The `field_mappings` array shows which input fields were mapped to which output fields, detected by value matching.

#### `transform_error`

Emitted when a record fails to transform.

```json
{"jsonrpc": "2.0", "method": "transform_error", "params": {
  "record_id": "page_123",
  "index": 0,
  "input_data": {"id": "page_123"},
  "error": "KeyError: 'title'",
  "error_type": "KeyError",
  "traceback": "..."
}}
```

#### `execution_complete`

Emitted when the entire execution finishes (success or failure).

```json
{"jsonrpc": "2.0", "method": "execution_complete", "params": {
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "total_records": 42,
  "successful_records": 40,
  "failed_records": 2,
  "total_duration_ms": 5678.9
}}
```

#### `heartbeat`

Emitted every 2 seconds during long-running phases (e.g., waiting on an external API).

```json
{"jsonrpc": "2.0", "method": "heartbeat", "params": {
  "phase": "get_data",
  "elapsed_seconds": 12.5,
  "message": "Working on get_data..."
}}
```

#### `log`

General-purpose log messages from the worker or connector.

```json
{"jsonrpc": "2.0", "method": "log", "params": {
  "level": "info",
  "message": "Found connector: MyConnector",
  "source": "MyConnector"
}}
```

## Connector Discovery

The worker discovers connectors by scanning Python files in the project directory. It searches:

- The project root
- `src/` subdirectory
- `connectors/` subdirectory

Files in `__pycache__`, `.venv`, `venv`, `node_modules`, and test files are skipped.

For each Python file, the worker imports the module and checks for classes that:

1. **Subclass SDK base classes** — `BaseDatasourceConnector`, `BaseStreamingDatasourceConnector`, `BaseAsyncStreamingDatasourceConnector`, `BasePeopleConnector`
2. **Match by heuristic** — classes with methods like `get_data`, `transform`, `index_data` (fallback when SDK base classes aren't on the import path)

Data clients are discovered the same way and linked to connectors by matching the generic type parameter (e.g., `BaseDatasourceConnector[MyData]` is linked to `BaseDataClient[MyData]`).

## Execution Modes

### Mock Data

If a `mock_data.json` or `test_data.json` file exists in the project root (or is specified via `mock_data_path`), the worker uses it instead of calling the real data client. The file should contain either:

- A JSON array of records: `[{"id": "1", ...}, ...]`
- An object with a `records` key: `{"records": [...]}`

Mock mode is useful for testing the transform logic without needing API credentials or network access.

### Real Data

If no mock data is found, the worker attempts to instantiate the connector's data client and fetch real data. It tries several strategies to construct the data client:

1. No-argument constructor
2. Constructor parameters inferred from environment variables (e.g., `API_URL` → `api_url` param)
3. All parameters set to `None`

Both sync and async data clients are supported — sync iterables are automatically wrapped into async iterators.

### Step Mode

When `step_mode: true` is passed to `execute`, the worker pauses after each record and waits for a `step` request before continuing. This enables record-by-record inspection of the fetch and transform phases.

## Execution States

```
PENDING → RUNNING → COMPLETED
                  → ABORTED (via abort request)
                  → ERROR (unhandled exception)
         RUNNING ↔ PAUSED (via pause/resume)
```

## Error Codes

Standard JSON-RPC error codes plus worker-specific extensions:

| Code | Name | Description |
|---|---|---|
| `-32700` | Parse error | Invalid JSON received |
| `-32600` | Invalid request | Missing `method` or `id` |
| `-32601` | Method not found | Unknown method name |
| `-32602` | Invalid params | Bad parameters for a method |
| `-32603` | Internal error | Unhandled exception |
| `-32000` | Connector not found | Named connector not found in project |
| `-32001` | Execution error | Error during connector execution, or execution already in progress |
| `-32002` | Project error | Error discovering or loading the project |
