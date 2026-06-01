# Observability Implementation Review

**Date:** 2026-06-01  
**Reviewer:** Claude  
**Branches Reviewed:** `feature/v0-workstream`, `feature/structured-logging`

---

## Executive Summary

✅ **Recommendation:** The implementation plan is solid and well-aligned with the design doc. Ready to proceed with minor adjustments noted below.

**Current State:**
- Structured logging formatters: ✅ **Complete** (on `feature/structured-logging`)
- Lifecycle integration: ❌ **Not started**
- Metrics provider system: ❌ **Not started**

**Key Findings:**
1. ✅ Strong observability hooks already exist in `BaseDatasourceConnector.index_data()`
2. ✅ Perfect integration points identified for lifecycle events and metrics
3. ⚠️ Need to align with existing `ConnectorMetrics` in `common/metrics.py`
4. ⚠️ Should wrap `api_client()` calls for request-level metrics
5. ✅ Batch upload logic is centralized and easy to instrument

---

## 1. Current Architecture Analysis

### 1.1 Existing Observability Infrastructure

**File:** `src/glean/indexing/observability/observability.py`

```python
class ConnectorObservability:
    def __init__(self, connector_name: str):
        self.connector_name = connector_name
        self.metrics: Dict[str, Any] = defaultdict(int)
        self.timers: Dict[str, float] = {}
        
    def start_execution()  # ✅ Called at index_data start
    def end_execution()    # ✅ Called at index_data end
    def record_metric()
    def increment_counter()
    def start_timer()
    def end_timer()
```

**Current Usage in BaseDatasourceConnector:**
```python
def index_data(self, mode, options):
    self._observability.start_execution()  # LINE 139
    try:
        # Identity crawl
        self._batch_index_users(users)     # LINE 150 - metrics hook needed
        self._batch_index_groups(groups)   # LINE 154 - metrics hook needed
        
        # Content crawl
        self._observability.start_timer("data_fetch")  # LINE 175
        data = self.get_data(since=since)
        self._observability.end_timer("data_fetch")    # LINE 177
        
        self._observability.record_metric("items_fetched", len(data))  # LINE 180
        
        self._observability.start_timer("data_transform")  # LINE 182
        documents = self.transform(data)
        self._observability.end_timer("data_transform")    # LINE 184
        
        self._observability.record_metric("documents_transformed", len(documents))  # LINE 187
        
        self._observability.start_timer("data_upload")  # LINE 189
        self._batch_index_documents(documents, options)  # LINE 192 - MAIN HOOK
        self._observability.end_timer("data_upload")      # LINE 193
        
        self._observability.record_metric("documents_indexed", len(documents))  # LINE 196
    except Exception as e:
        self._observability.increment_counter("indexing_errors")  # LINE 200
    finally:
        self._observability.end_execution()  # LINE 203
```

**Batch Upload Pattern (lines 295-344):**
```python
def _batch_index_documents(self, documents, options):
    batches = list(BatchProcessor(documents, batch_size=self.batch_size))
    total_batches = len(batches)
    upload_id = str(uuid.uuid4())
    
    for i, batch in enumerate(batches):
        try:
            with api_client() as client:  # ⚠️ API instrumentation point
                client.indexing.documents.bulk_index(
                    datasource=self.name,
                    documents=list(batch),
                    upload_id=upload_id,
                    is_first_page=(i == 0),
                    is_last_page=(i == total_batches - 1),
                    # ... options
                )
            
            logger.info(f"Document batch {i + 1}/{total_batches} uploaded")
            self._observability.increment_counter("batches_uploaded")  # LINE 339
        except Exception as e:
            logger.error(f"Failed to upload batch: {e}")
            self._observability.increment_counter("batch_upload_errors")  # LINE 343
```

### 1.2 Existing Components to Consider

**ConnectorMetrics (common/metrics.py):**
```python
class ConnectorMetrics:
    """A context manager for tracking connector metrics."""
    def __init__(self, name: str, logger: Optional[logging.Logger] = None)
    def __enter__() -> "ConnectorMetrics"
    def __exit__()
    def record(self, metric: str, value: Any) -> None
```

⚠️ **Action Required:** This overlaps with `ConnectorObservability.record_metric()`. We should:
- Option A: Deprecate `ConnectorMetrics` and migrate functionality to `ConnectorObservability`
- Option B: Keep both but document clear use cases (ConnectorMetrics for ad-hoc, ConnectorObservability for lifecycle)
- **Recommendation:** Option A - consolidate into ConnectorObservability

### 1.3 API Client Architecture

**File:** `src/glean/indexing/common/glean_client.py`

```python
def api_client() -> Glean:
    """Get the Glean API client."""
    server_url = os.getenv("GLEAN_SERVER_URL")
    api_token = os.getenv("GLEAN_INDEXING_API_TOKEN")
    
    return Glean(api_token=api_token, server_url=server_url, timeout_ms=DEFAULT_TIMEOUT_MS)
```

⚠️ **Critical for P0 Metrics:**
- This is used in **every** API call via `with api_client() as client:`
- To capture `api_request_latency_ms`, `api_request_count`, `api_request_errors`, we need to instrument this
- **Two approaches:**
  1. Wrap the Glean client with an instrumented proxy
  2. Add context manager hooks to time calls
- **Recommendation:** Add instrumented wrapper in observability module

---

## 2. Implementation Plan Review

### 2.1 PR 1: Structured Logging ✅

**Status:** Well-planned, ready to implement

**Additions Based on Code Review:**

#### 2.1.1 Add run_id to ConnectorObservability
```python
class ConnectorObservability:
    def __init__(
        self,
        connector_name: str,
        datasource: Optional[str] = None,
        crawl_mode: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.connector_name = connector_name
        self.datasource = datasource or connector_name  # ✅ Default to connector_name
        self.crawl_mode = crawl_mode  # Will be set from IndexingMode
        self.run_id = run_id or str(uuid.uuid4())
        # ... existing code
```

**⚠️ Update Required:** `BaseDatasourceConnector.__init__` to pass datasource:
```python
# Line 61 - current
self._observability = ConnectorObservability(name)

# Proposed
self._observability = ConnectorObservability(
    connector_name=name,
    datasource=self.configuration.name if hasattr(self, 'configuration') else name
)
```

**⚠️ Update Required:** `index_data()` to set crawl_mode:
```python
def index_data(self, mode: IndexingMode, options):
    self._observability.crawl_mode = mode.value  # ✅ Set before start_execution
    self._observability.start_execution()
```

#### 2.1.2 Lifecycle Events - Exact Integration Points

**In `index_data()` method (base_datasource_connector.py):**

| Line | Current Code | Event to Emit |
|------|--------------|---------------|
| 139 | `self._observability.start_execution()` | `crawl_started` |
| 144 | `logger.info("Starting identity crawl")` | `identity_crawl_started` |
| 150 | `self._batch_index_users(users)` | After: `users_indexed` |
| 154 | `self._batch_index_groups(groups)` | After: `groups_indexed` |
| 174 | `logger.info("Starting content crawl")` | `content_crawl_started` |
| 175-177 | Timer: `data_fetch` | `data_fetch_started`, `data_fetch_completed` |
| 182-184 | Timer: `data_transform` | `transform_started`, `transform_completed` |
| 189-193 | Timer: `data_upload` | Handled in batch methods |
| 203 | `self._observability.end_execution()` | `crawl_completed` |
| 200 | Exception handler | `crawl_failed` |

**In batch methods (_batch_index_documents, etc.):**

| Line | Current Code | Event to Emit |
|------|--------------|---------------|
| 313 | Start of batch loop | `batch_upload_started` (per batch) |
| 338 | Success log | `batch_upload_completed` (per batch) |
| 342 | Error log | `batch_upload_failed` (per batch) |

**Common Log Fields Structure:**
```python
def _get_common_fields(self, operation: str = None, **kwargs) -> dict:
    """Get common fields for structured logging."""
    fields = {
        "connector": self.connector_name,
        "datasource": self.datasource,
        "crawl_mode": self.crawl_mode,
        "run_id": self.run_id,
    }
    if operation:
        fields["operation"] = operation
    fields.update(kwargs)
    return fields
```

### 2.2 PR 2: Metrics Provider System ✅

**Status:** Well-planned with critical additions needed

#### 2.2.1 MetricsProvider Interface ✅
Plan is solid. Additions:

```python
from enum import Enum

class MetricType(str, Enum):
    """Standard metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"

class MetricsProvider(ABC):
    @abstractmethod
    def emit_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        pass
    
    @abstractmethod
    def emit_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        pass
    
    @abstractmethod
    def emit_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram value."""
        pass
    
    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered metrics."""
        pass
```

**Reasoning:** Different backends handle different metric types differently (Counter vs Gauge vs Histogram in CloudWatch/GCP Monitoring).

#### 2.2.2 P0 Metrics Integration Points

Based on code review, here are the **exact** integration points:

**1. upload_batch_size** (gauge)
```python
# File: base_datasource_connector.py, _batch_index_documents()
# Line 316 - inside batch loop
batch_size = len(batch)
self._observability.record_metric(
    "upload_batch_size",
    batch_size,
    metric_type=MetricType.GAUGE,
    labels={"batch_index": str(i), "entity_type": "document"}
)
```

**2. upload_throughput** (gauge)
```python
# File: base_datasource_connector.py, _batch_index_documents()
# Line 338 - after successful upload
duration = time.time() - batch_start_time
docs_per_sec = len(batch) / duration if duration > 0 else 0
self._observability.record_metric(
    "upload_throughput",
    docs_per_sec,
    metric_type=MetricType.GAUGE,
    labels={"batch_index": str(i)}
)
```

**3. api_request_latency_ms, api_request_count, api_request_errors** (histogram, counter, counter)
```python
# File: observability/api_instrumentation.py (NEW)
class InstrumentedGleanClient:
    """Wrapper around Glean client that emits observability metrics."""
    
    def __init__(self, client: Glean, observability: ConnectorObservability):
        self._client = client
        self._observability = observability
    
    def __enter__(self):
        self._start_time = time.time()
        return self._client.__enter__()
    
    def __exit__(self, *args):
        duration_ms = (time.time() - self._start_time) * 1000
        # Emit metrics
        self._observability.record_metric("api_request_latency_ms", duration_ms, ...)
        return self._client.__exit__(*args)

# Usage: Modify api_client() to accept observability
def api_client(observability: Optional[ConnectorObservability] = None) -> Glean:
    client = Glean(...)
    if observability:
        return InstrumentedGleanClient(client, observability)
    return client
```

⚠️ **Challenge:** `api_client()` is a module-level function, not a method. We need to:
- Option A: Add optional observability parameter to `api_client()`
- Option B: Create `ConnectorObservability.instrumented_api_client()` method
- **Recommendation:** Option A for backward compatibility

**4. retry_count** (counter)
⚠️ **Note from design doc:** "Defined here, implemented by Pull / Push workstreams"
- The retry logic is not in the SDK yet
- When retry logic is added, it should call `observability.record_metric("retry_count", 1, ...)`
- For now, we just **define** the metric in documentation, no implementation

**5. crawl_success / crawl_failure** (counter)
```python
# File: base_datasource_connector.py, index_data()
# Line 203 - in finally block
def end_execution(self):
    if self.start_time:
        duration = time.time() - self.start_time
        self.record_metric("total_execution_time", duration)
        
        # ✅ Add success metric
        self.record_metric("crawl_success", 1, metric_type=MetricType.COUNTER)
        
        logger.info(...)

# Line 200 - in exception handler
except Exception as e:
    logger.exception(...)
    self.increment_counter("indexing_errors")
    
    # ✅ Add failure metric
    self.record_metric("crawl_failure", 1, 
                      metric_type=MetricType.COUNTER,
                      labels={"error_type": type(e).__name__})
    raise
```

#### 2.2.3 Cloud Providers Structure

**Directory Structure:**
```
src/glean/indexing/observability/
├── __init__.py
├── observability.py
├── formatters.py
├── providers.py           # ✅ NEW: MetricsProvider ABC + InMemory
├── api_instrumentation.py # ✅ NEW: InstrumentedGleanClient
└── cloud/
    ├── __init__.py
    ├── gcp.py             # ✅ NEW: GCP provider + helpers
    └── aws.py             # ✅ NEW: AWS provider + helpers
```

**Dependencies (pyproject.toml):**
```toml
[project.optional-dependencies]
gcp = [
    "google-cloud-logging>=3.10.0",
    "google-cloud-monitoring>=2.21.0",
]
aws = [
    "boto3>=1.34.0",
    "watchtower>=3.1.0",
]
```

---

## 3. Key Adjustments to Implementation Plan

### 3.1 Handle ConnectorMetrics Coexistence

**Action:** Keep both classes - they serve different purposes:
- **ConnectorMetrics**: Ad-hoc metrics for custom connector code (user-owned)
- **ConnectorObservability**: SDK lifecycle metrics (SDK-owned)
- **Enhancement**: Optionally add `metrics_provider` parameter to ConnectorMetrics for consistency
- **Document**: Clear use case documentation for when to use each
- **Backward Compatible**: ✅ No breaking changes

### 3.2 API Client Instrumentation Strategy

**Action:** In PR 2, add:
```python
# observability/api_instrumentation.py
def instrumented_api_client(
    observability: Optional[ConnectorObservability] = None
) -> Glean:
    """Get API client with optional observability instrumentation."""
    # Implementation
```

Then update `BaseDatasourceConnector` batch methods:
```python
# Before (line 324)
with api_client() as client:

# After
with instrumented_api_client(self._observability) as client:
```

### 3.3 Metric Type Differentiation

**Action:** In PR 2, add `MetricType` enum and update method signatures:
```python
def record_metric(
    self,
    key: str,
    value: float,
    metric_type: MetricType = MetricType.GAUGE,
    labels: Optional[Dict[str, str]] = None,
):
```

### 3.4 Testing Strategy Enhancement

**Add to Test Plan:**

**PR 1 Tests:**
- `test_observability_run_id_auto_generation.py`
- `test_observability_crawl_mode_tracking.py`
- `test_lifecycle_events_with_structured_formatter.py`
- `test_common_fields_included_in_all_events.py`
- `test_backward_compatibility_no_structured_logging.py`

**PR 2 Tests:**
- `test_metrics_provider_interface.py`
- `test_in_memory_provider_backward_compatibility.py`
- `test_api_client_instrumentation.py` (with mocked Glean client)
- `test_p0_metrics_emission.py` (verify each P0 metric)
- `test_cloud_providers_lazy_import.py` (ensure no ImportError without extras)
- `test_gcp_provider_with_mocked_client.py`
- `test_aws_provider_with_mocked_client.py`

---

## 4. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Confusion between ConnectorMetrics and ConnectorObservability | Low | Clear documentation on use cases for each |
| api_client() signature change breaks existing code | Medium | Make observability parameter optional with default None |
| Cloud extras import errors | Low | Lazy imports + comprehensive tests |
| Performance overhead from metrics emission | Low | In-memory provider is lightweight, cloud providers buffer |
| Label cardinality explosion | Medium | Document label best practices, limit to connector/datasource/operation |

---

## 5. Success Criteria Checklist

### PR 1: Structured Logging
- [ ] StructuredFormatter works with stdlib handlers
- [ ] run_id auto-generated and included in all lifecycle events
- [ ] Common fields (connector, datasource, crawl_mode, run_id) in all events
- [ ] Lifecycle events emitted at correct points
- [ ] Backward compatible (no structured logging by default)
- [ ] Documentation with examples
- [ ] All tests passing
- [ ] No regressions in existing connectors

### PR 2: Metrics Provider
- [ ] MetricsProvider ABC is clean and extensible
- [ ] InMemoryMetricsProvider maintains backward compatibility
- [ ] P0 metrics auto-emit from lifecycle hooks
- [ ] API client instrumentation works
- [ ] GCP provider works with `pip install glean-indexing-sdk[gcp]`
- [ ] AWS provider works with `pip install glean-indexing-sdk[aws]`
- [ ] Base SDK imports without extras (no ImportError)
- [ ] Documentation with custom provider example
- [ ] All tests passing

---

## 6. Recommendations

### 6.1 Immediate Actions
1. ✅ Proceed with implementation as planned
2. ✅ Incorporate adjustments from sections 3.1-3.4
3. ✅ Add `MetricType` enum to providers.py
4. ✅ Create `api_instrumentation.py` for instrumented client

### 6.2 Follow-up Work (Post-PRs)
1. Create example connector demonstrating observability features
2. Add cookbook entry for custom MetricsProvider
3. Create observability troubleshooting guide
4. Document ConnectorMetrics vs ConnectorObservability use cases in SDK guide

### 6.3 Coordination with Other Workstreams
- **Pull Layer:** When retry logic is added, use `observability.record_metric("retry_count", ...)`
- **Persistence:** When checkpoints are implemented, use `checkpoint_save_latency_ms` metric
- **Push Layer:** Coordinate on API client instrumentation approach

---

## 7. Conclusion

✅ **The implementation plan is excellent and ready to execute.**

**Key Strengths:**
- Well-aligned with design doc
- Strong integration points identified
- Extensibility built in
- Backward compatibility preserved

**Adjustments Needed:**
- Handle ConnectorMetrics overlap
- Add API client instrumentation
- Differentiate metric types
- Enhanced test coverage

**Next Step:** Begin PR 1 implementation with adjustments incorporated.

---

**Reviewed By:** Claude  
**Date:** 2026-06-01  
**Status:** ✅ APPROVED TO PROCEED
