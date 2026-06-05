# Glean Indexing SDK - Repository Structure & Components

## 📁 Repository Overview

```
glean-indexing-sdk/
├── src/glean/indexing/          # Main SDK code
│   ├── connectors/              # Base connector classes
│   ├── common/                  # Shared utilities
│   ├── observability/          # Logging & metrics infrastructure
│   │   └── plugins/            # Cloud provider integrations (AWS, GCP)
│   ├── testing/                # Test utilities & mocks
│   ├── worker/                 # Background worker infrastructure
│   ├── models.py               # Data models & type definitions
│   └── exceptions.py           # Custom exceptions
├── tests/                      # Test suite
│   ├── unit_tests/            # Unit tests
│   │   └── observability/
│   │       └── plugins/       # Cloud plugin tests
│   └── integration_tests/     # Integration tests
├── docs/                      # Documentation
├── recipes/                   # Example implementations
└── pyproject.toml            # Project configuration
```

---

## 🏗️ Core Architecture

### The Three-Layer Pattern

The SDK follows a **fetch → transform → upload** pattern:

1. **DataClient Layer** - Fetches raw data from external systems
2. **Connector Layer** - Transforms data to Glean format
3. **Upload Layer** - Batches and sends to Glean API

```
External System (API/DB/Files)
       ↓
   DataClient (fetch)
       ↓
   Connector (transform)
       ↓
   Glean API (upload)
```

---

## 📦 Component Breakdown

### 1. **Connectors (`src/glean/indexing/connectors/`)**

The heart of the SDK - base classes for building custom connectors.

#### Connector Types

| File | Class | Use Case |
|------|-------|----------|
| `base_connector.py` | `BaseConnector` | Abstract base for all connectors |
| `base_datasource_connector.py` | `BaseDatasourceConnector[T]` | Small-to-medium datasets (fits in memory) |
| `base_streaming_datasource_connector.py` | `BaseStreamingDatasourceConnector[T]` | Large datasets with sync generators |
| `base_async_streaming_datasource_connector.py` | `BaseAsyncStreamingDatasourceConnector[T]` | Large datasets with async I/O |
| `base_people_connector.py` | `BasePeopleConnector` | Employee/identity indexing |

#### Data Client Types

| File | Class | Use Case |
|------|-------|----------|
| `base_data_client.py` | `BaseDataClient[T]` | Returns all data at once (`Sequence[T]`) |
| `base_streaming_data_client.py` | `BaseStreamingDataClient[T]` | Yields data incrementally (`Generator[T]`) |
| `base_async_streaming_data_client.py` | `BaseAsyncStreamingDataClient[T]` | Async data streaming (`AsyncGenerator[T]`) |

**Key Methods:**
- `get_source_data(since=None)` - Fetch data from external system
- `transform(data)` - Convert to Glean's `DocumentDefinition`
- `index_data(mode=...)` - Execute the indexing pipeline

---

### 2. **Common Utilities (`src/glean/indexing/common/`)**

Shared utilities used across the SDK.

| File | Purpose |
|------|---------|
| `glean_client.py` | Wrapper around Glean API client with error handling |
| `batch_processor.py` | Batches documents for efficient API uploads |
| `content_formatter.py` | Formats content (text, HTML, markdown) for Glean |
| `property_definition_builder.py` | Builds custom property definitions |
| `metrics.py` | **(Legacy)** Basic metrics tracking (replaced by observability) |

**Key Classes:**
- `GleanClient` - Handles API authentication, retries, rate limiting
- `BatchProcessor` - Chunks data into batches (default 100 items)
- `ContentFormatter` - Sanitizes and formats document content

---

### 3. **Observability (`src/glean/indexing/observability/`)**

**NEW SYSTEM** - Comprehensive logging and metrics infrastructure.

#### Core Components

| File | Purpose |
|------|---------|
| `observability.py` | Central observability orchestrator |
| `formatters.py` | Structured JSON logging formatters |
| `logging.py` | LoggerProvider ABC for pluggable logging backends |
| `providers.py` | MetricsProvider ABC for pluggable metrics backends |

#### Architecture Pattern

```
ConnectorObservability
    ├── LoggerProvider (where logs go)
    │   ├── ConsoleLoggerProvider (default, stdout)
    │   ├── CloudWatchLogsProvider (AWS)
    │   └── CloudLoggingProvider (GCP)
    │
    └── MetricsProvider (where metrics go)
        ├── InMemoryMetricsProvider (default, testing)
        ├── CloudWatchMetricsProvider (AWS)
        └── CloudMonitoringProvider (GCP)
```

#### Key Features

**1. Lifecycle Event Logging**
```python
obs = ConnectorObservability("my_connector", datasource="salesforce", crawl_mode="incremental")

obs.start_execution()                    # Logs: crawl_started
obs.log_data_fetch_started()             # Logs: data_fetch_started
obs.log_data_fetch_completed(count, ms)  # Logs: data_fetch_completed
obs.log_transform_started(count)         # Logs: transform_started
obs.log_transform_completed(...)         # Logs: transform_completed
obs.log_batch_upload_started(...)        # Logs: batch_upload_started
obs.log_batch_upload_completed(...)      # Logs: batch_upload_completed
obs.end_execution()                      # Logs: crawl_completed
```

**2. Structured Logging**
- `StructuredFormatter` - JSON output with full metadata
- `CompactStructuredFormatter` - JSON output, omits null/empty fields
- All logs include: `run_id`, `connector`, `datasource`, `operation`, `timestamp`

**3. Metrics Emission**
```python
obs.record_upload_batch_size(100)
obs.record_upload_throughput(50.5)
obs.record_api_request_latency(250.0, endpoint="/documents")
obs.record_api_request_count(endpoint="/documents")
obs.record_api_request_error(endpoint="/documents", error_type="RateLimitError")
```

**4. Performance Tracking**
```python
# Context manager
with PerformanceTracker("fetch_data", obs):
    data = fetch_from_api()

# Decorator
@with_observability()
class MyConnector:
    pass  # All public methods auto-logged

# Progress tracking
progress = ProgressCallback(total_items=1000)
for batch in batches:
    process(batch)
    progress.update(len(batch))
progress.complete()
```

---

### 4. **Cloud Plugins (`src/glean/indexing/observability/plugins/`)**

**Optional dependencies** for cloud provider integrations.

#### AWS Plugins (`observability/plugins/aws/`)

| File | Provider | Purpose |
|------|----------|---------|
| `cloudwatch_logs.py` | `CloudWatchLogsProvider` | Send logs to AWS CloudWatch Logs |
| `cloudwatch_metrics.py` | `CloudWatchMetricsProvider` | Send metrics to AWS CloudWatch Metrics |

**Installation:** `pip install glean-indexing-sdk[aws]`

**Dependencies:** `boto3`, `watchtower`

**Features:**
- Auto-creates log groups and streams
- Buffered metrics (up to 20 per batch, CloudWatch limit)
- Custom dimensions support
- Region-specific clients

#### GCP Plugins (`observability/plugins/gcp/`)

| File | Provider | Purpose |
|------|----------|---------|
| `cloud_logging.py` | `CloudLoggingProvider` | Send logs to GCP Cloud Logging |
| `cloud_monitoring.py` | `CloudMonitoringProvider` | Send metrics to GCP Cloud Monitoring |

**Installation:** `pip install glean-indexing-sdk[gcp]`

**Dependencies:** `google-cloud-logging`, `google-cloud-monitoring`

**Features:**
- Structured logging with resource labels
- Custom metric types (GAUGE, COUNTER, HISTOGRAM/DISTRIBUTION)
- Monitored resource configuration (GCE, K8s, etc.)
- High buffer capacity (200 metrics)

---

### 5. **Testing Infrastructure (`src/glean/indexing/testing/`)**

Complete testing utilities for connector development.

| File | Purpose |
|------|---------|
| `mock_client.py` | Mock Glean API client for tests |
| `data_clients.py` | Static data clients for testing |
| `runner.py` | Test runner helpers |
| `fixtures.py` | Pytest fixtures |

**Key Components:**

**1. Mock Glean Client**
```python
from glean.indexing.testing import mock_glean_client

with mock_glean_client() as client:
    connector.configure_datasource()
    connector.index_data(mode=IndexingMode.FULL)
    
    # Assertions
    client.assert_datasource_configured(name="my_ds")
    client.assert_documents_posted(count=10, datasource="my_ds")
    
    # Access posted data
    for doc in client.documents_posted:
        print(doc.title)
```

**2. Static Data Clients**
```python
from glean.indexing.testing import StaticDataClient, StaticStreamingDataClient

# For BaseDatasourceConnector
client = StaticDataClient([{"id": "1", "title": "Doc 1"}, ...])

# For BaseStreamingDatasourceConnector
client = StaticStreamingDataClient([{"id": "1", "title": "Doc 1"}, ...])

# For BaseAsyncStreamingDatasourceConnector
client = StaticAsyncStreamingDataClient([{"id": "1", "title": "Doc 1"}, ...])
```

**3. Test Runners**
```python
from glean.indexing.testing import run_connector, run_connector_async

# Sync connectors
result = run_connector(MyConnector("ds", StaticDataClient([...])))
result.assert_documents_posted(count=5)

# Async connectors
result = await run_connector_async(MyAsyncConnector("ds", StaticAsyncStreamingDataClient([...])))
result.assert_documents_posted(count=5)
```

---

### 6. **Worker System (`src/glean/indexing/worker/`)**

Background worker infrastructure for scheduled/async indexing.

| File | Purpose |
|------|---------|
| `main.py` | Worker entry point |
| `executor.py` | Task execution engine |
| `discovery.py` | Auto-discovers connectors |
| `handlers.py` | Request handlers |
| `protocol.py` | Worker protocol definitions |

**Use Case:**
- Run connectors on a schedule
- Deploy as a service
- Async task processing

---

### 7. **Models & Types (`src/glean/indexing/models.py`)**

Core data models used throughout the SDK.

**Key Models:**
- `DocumentDefinition` - Represents a document to index
- `EmployeeInfoDefinition` - Employee/identity data
- `ContentDefinition` - Document content (text, HTML, etc.)
- `UserReferenceDefinition` - User references
- `CustomDatasourceConfig` - Datasource configuration
- `IndexingMode` - FULL vs INCREMENTAL enum

---

## 🔄 Data Flow Example

Here's how a typical connector works:

```python
# 1. Define your data structure
class WikiPage(TypedDict):
    id: str
    title: str
    content: str
    author: str

# 2. Create data client (fetch layer)
class WikiDataClient(BaseDataClient[WikiPage]):
    def get_source_data(self, since=None) -> Sequence[WikiPage]:
        # Fetch from external API
        return fetch_wiki_pages()

# 3. Create connector (transform layer)
class WikiConnector(BaseDatasourceConnector[WikiPage]):
    configuration = CustomDatasourceConfig(
        name="wiki",
        display_name="Company Wiki"
    )
    
    def transform(self, data: Sequence[WikiPage]) -> List[DocumentDefinition]:
        # Convert to Glean format
        return [DocumentDefinition(
            id=page["id"],
            title=page["title"],
            body=ContentDefinition(text_content=page["content"]),
            datasource="wiki"
        ) for page in data]

# 4. Run (upload layer)
client = WikiDataClient()
connector = WikiConnector("wiki", client)

# With observability
obs = ConnectorObservability("wiki", datasource="company_wiki")
connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
```

**Internal Flow:**
```
User calls: connector.index_data()
    ↓
Connector calls: data_client.get_source_data()
    ↓
Data flows: External API → DataClient → Connector
    ↓
Connector calls: self.transform(data)
    ↓
BatchProcessor chunks into batches of 100
    ↓
For each batch:
    - ObservabilityProvider logs: batch_upload_started
    - GleanClient uploads via API
    - ObservabilityProvider logs: batch_upload_completed
    - MetricsProvider records: batch_size, throughput, latency
    ↓
Complete!
```

---

## 🎯 Design Principles

### 1. **Provider Pattern**
All external integrations use ABC providers:
- `LoggerProvider` - Pluggable logging backends
- `MetricsProvider` - Pluggable metrics backends
- `BaseDataClient` - Pluggable data sources

### 2. **Type Safety**
- Generic types (`T`) for data structures
- TypedDict for data schemas
- Full type hints throughout

### 3. **Zero-Dependency Base**
- Core SDK has no cloud dependencies
- Cloud plugins are optional extras: `[aws]`, `[gcp]`
- Falls back gracefully if optional deps missing

### 4. **Testability First**
- Mock clients for testing without API calls
- Static data clients for deterministic tests
- Assertion helpers for common checks

### 5. **Observability by Default**
- Structured logging out of the box
- Lifecycle events tracked automatically
- Metrics emitted for all operations
- Easy integration with cloud providers

---

## 📊 Observability System Deep Dive

### Event Correlation

All logs from a single crawl share the same `run_id`:

```json
{
  "timestamp": "2026-06-05T10:00:00.000Z",
  "level": "INFO",
  "message": "Crawl started",
  "connector": "salesforce_connector",
  "datasource": "salesforce",
  "crawl_mode": "incremental",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "operation": "crawl_started"
}
```

Query logs by `run_id` to trace entire execution.

### Metric Types

**COUNTER** - Cumulative count
```python
obs.record_api_request_count(endpoint="/documents")  # +1
```

**GAUGE** - Point-in-time value
```python
obs.record_upload_throughput(docs_per_sec=45.5)  # Current rate
```

**HISTOGRAM** - Distribution of values
```python
obs.record_api_request_latency(latency_ms=250.0, endpoint="/documents")
```

### Cloud Integration Examples

**AWS CloudWatch:**
```python
from glean.indexing.observability import ConnectorObservability
from glean.indexing.observability.plugins.aws import CloudWatchLogsProvider, CloudWatchMetricsProvider

logger_provider = CloudWatchLogsProvider(
    log_group="/glean/connectors",
    log_stream="salesforce-prod",
    region_name="us-east-1"
)

metrics_provider = CloudWatchMetricsProvider(
    namespace="GleanConnectors",
    region_name="us-east-1",
    dimensions={"environment": "prod", "connector": "salesforce"}
)

obs = ConnectorObservability(
    connector_name="salesforce",
    logger_provider=logger_provider,
    metrics_provider=metrics_provider
)
```

**GCP Cloud Logging/Monitoring:**
```python
from glean.indexing.observability import ConnectorObservability
from glean.indexing.observability.plugins.gcp import CloudLoggingProvider, CloudMonitoringProvider

logger_provider = CloudLoggingProvider(
    project_id="my-project",
    log_name="glean-connectors",
    resource_type="gce_instance",
    resource_labels={"zone": "us-central1-a"}
)

metrics_provider = CloudMonitoringProvider(
    project_id="my-project",
    resource_type="gce_instance",
    resource_labels={"zone": "us-central1-a"}
)

obs = ConnectorObservability(
    connector_name="salesforce",
    logger_provider=logger_provider,
    metrics_provider=metrics_provider
)
```

---

## 🧪 Testing Strategy

### Test Levels

**1. Unit Tests** (`tests/unit_tests/`)
- Test individual components in isolation
- Mock external dependencies
- Fast execution

**2. Integration Tests** (`tests/integration_tests/`)
- Test connector pipeline end-to-end
- Use real Glean API (staging)
- Slower but comprehensive

### Test Organization

```
tests/
├── unit_tests/
│   ├── connectors/          # Connector base class tests
│   ├── common/              # Utility tests
│   ├── observability/       # Logging & metrics tests
│   ├── plugins/
│   │   ├── aws/            # AWS plugin tests
│   │   └── gcp/            # GCP plugin tests
│   └── testing/            # Test infrastructure tests
└── integration_tests/
    └── connectors/         # Full connector tests
```

---

## 🔧 Development Workflow

### Setup
```bash
mise run setup              # Install deps
mise run test               # Run tests
mise run lint               # Check code quality
mise run lint:fix           # Auto-fix issues
```

### Adding a New Feature

1. **Create branch:** `git checkout -b feature/my-feature`
2. **Write tests first:** `tests/unit_tests/my_feature_test.py`
3. **Implement:** `src/glean/indexing/my_feature.py`
4. **Run tests:** `mise run test`
5. **Lint:** `mise run lint:fix`
6. **Commit:** Use conventional commits (feat:, fix:, etc.)
7. **PR:** Create PR with clear description

### Adding Cloud Provider Support

1. Create plugin directory: `src/glean/indexing/plugins/{provider}/`
2. Implement LoggerProvider and/or MetricsProvider
3. Add optional dependency to `pyproject.toml`
4. Write tests with `pytest.importorskip()`
5. Add recipe examples
6. Update documentation

---

## 📚 Key Files Reference

| File | Purpose |
|------|---------|
| `pyproject.toml` | Dependencies, build config, tool config |
| `README.md` | User-facing documentation |
| `CONTRIBUTING.md` | Contributor guide |
| `CHANGELOG.md` | Version history |
| `docs/architecture.md` | Architecture diagrams |
| `docs/streaming-connectors.md` | Streaming connector guide |
| `docs/advanced.md` | Advanced usage patterns |
| `recipes/` | Example connector implementations |

---

## 🎓 Learning Path

**Beginner:**
1. Read `README.md`
2. Build the quickstart connector
3. Run tests with `StaticDataClient`

**Intermediate:**
4. Read `docs/architecture.md`
5. Implement a streaming connector
6. Add structured logging

**Advanced:**
7. Build custom cloud provider plugin
8. Implement custom MetricsProvider
9. Deploy with worker system

---

## 🔍 Common Patterns

### Pattern 1: Simple Document Indexing
```python
class MyDataClient(BaseDataClient[MyData]):
    def get_source_data(self, since=None):
        return fetch_all_data()

class MyConnector(BaseDatasourceConnector[MyData]):
    def transform(self, data):
        return [DocumentDefinition(...) for item in data]
```

### Pattern 2: Incremental Indexing
```python
def get_source_data(self, since=None):
    if since:
        return fetch_data_since(since)
    return fetch_all_data()

# Usage
connector.index_data(mode=IndexingMode.INCREMENTAL)
```

### Pattern 3: Async Streaming
```python
class MyDataClient(BaseAsyncStreamingDataClient[MyData]):
    async def get_source_data(self, since=None):
        async for page in paginate_api():
            for item in page:
                yield item

class MyConnector(BaseAsyncStreamingDatasourceConnector[MyData]):
    async def transform(self, data_stream):
        async for item in data_stream:
            yield DocumentDefinition(...)

# Usage
await connector.index_data_async(mode=IndexingMode.FULL)
```

---

This structure enables building robust, production-ready connectors with minimal boilerplate while maintaining flexibility for custom requirements.
