# SDK Observability Implementation Plan

Based on: [SDK Observability Design](https://docs.google.com/document/d/1V4-q8C4NvKkLy82fr2RWmlIFb-gDBqAtJx7PVMeAE4I)

## Current Status

### ✅ Completed (on `feature/structured-logging` branch)
- **StructuredFormatter** - JSON formatter for structured logging
- **CompactStructuredFormatter** - Compact JSON formatter that omits empty fields
- **Comprehensive formatter tests** - Full test coverage for both formatters
- **Updated __init__.py** - Exports new formatters

### 📋 To Implement

## PR 1: Structured Logging & Lifecycle Events

**Target Branch:** `feature/v0-workstream`  
**From Branch:** `feature/structured-logging` (rebase onto v0-workstream)

### Goals
1. Enhance ConnectorObservability with structured lifecycle logging
2. Add automatic run_id generation for correlation
3. Emit standardized lifecycle events with common fields
4. Make structured logging opt-in but easy to enable

### Implementation Tasks

#### 1.1 Enhance ConnectorObservability Class
**File:** `src/glean/indexing/observability/observability.py`

- [ ] Add `run_id` field (auto-generated UUID if not provided)
- [ ] Add `datasource` and `crawl_mode` fields
- [ ] Update `start_execution()` to emit structured "crawl_started" event
- [ ] Update `end_execution()` to emit structured "crawl_completed" event
- [ ] Add `fail_execution()` to emit structured "crawl_failed" event
- [ ] Add method to get common log fields dict for use in `extra={}`

Common fields for all lifecycle events:
```python
{
    "connector": self.connector_name,
    "datasource": self.datasource,
    "crawl_mode": self.crawl_mode,
    "run_id": self.run_id,
    "operation": "...",  # specific to event
    "duration_ms": ...,  # where applicable
    # ... event-specific fields
}
```

#### 1.2 Update Decorators for Structured Events
**File:** `src/glean/indexing/observability/observability.py`

- [ ] Update `@with_observability` to emit structured events with common fields
- [ ] Update `@track_crawl_progress` to emit structured events
- [ ] Update `PerformanceTracker` to support structured logging via `extra={}`

#### 1.3 Update setup_connector_logging
**File:** `src/glean/indexing/observability/observability.py`

- [ ] Add optional `use_structured_logging` parameter
- [ ] When enabled, attach StructuredFormatter to handlers
- [ ] Keep default behavior unchanged (backwards compatible)

Example:
```python
def setup_connector_logging(
    connector_name: str,
    log_level: str = "INFO",
    use_structured_logging: bool = False,
    formatter_class: Optional[Type[logging.Formatter]] = None,
):
    if use_structured_logging:
        formatter = formatter_class or StructuredFormatter()
    else:
        formatter = logging.Formatter(...)
```

#### 1.4 Add Lifecycle Event Helpers
**File:** `src/glean/indexing/observability/logging_helpers.py` (new)

Helper functions for emitting standardized events:
- [ ] `log_data_fetch_started()`
- [ ] `log_data_fetch_completed()`
- [ ] `log_transform_started()`
- [ ] `log_transform_completed()`
- [ ] `log_batch_upload_started()`
- [ ] `log_batch_upload_completed()`
- [ ] `log_batch_upload_failed()`

These should use logger.info/error with structured `extra={}` fields.

#### 1.5 Testing
**Files:** `tests/unit_tests/observability/test_lifecycle_logging.py` (new)

- [ ] Test run_id auto-generation
- [ ] Test lifecycle event emission (started/completed/failed)
- [ ] Test common fields are included in all events
- [ ] Test backwards compatibility (no structured logging by default)
- [ ] Test integration with StructuredFormatter
- [ ] Test decorator enhancements emit structured events

#### 1.6 Documentation
- [ ] Add docstring examples showing structured logging usage
- [ ] Update README with structured logging examples
- [ ] Document common log fields contract

---

## PR 2: Metrics Provider System

**Target Branch:** `feature/v0-workstream`  
**From Branch:** New branch from PR 1

### Goals
1. Create extensible MetricsProvider interface
2. Integrate metrics emission into ConnectorObservability
3. Implement P0 metrics at SDK lifecycle points
4. Add optional cloud provider helpers (GCP/AWS) with lazy imports
5. Keep in-memory metrics as default (zero-config)

### Implementation Tasks

#### 2.1 Create MetricsProvider Interface
**File:** `src/glean/indexing/observability/providers.py` (new)

**Note on ConnectorMetrics:** The existing `ConnectorMetrics` class in `common/metrics.py` will be kept for backward compatibility. It serves a different purpose (ad-hoc metrics in user code) vs `ConnectorObservability` (SDK lifecycle metrics). Optionally, we can enhance `ConnectorMetrics` to support a `metrics_provider` parameter for consistency.



```python
from abc import ABC, abstractmethod
from typing import Dict, Optional

class MetricsProvider(ABC):
    """Abstract interface for metrics emission backends."""
    
    @abstractmethod
    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: str = "gauge",  # gauge, counter, histogram
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Emit a single metric."""
        pass
    
    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered metrics."""
        pass


class InMemoryMetricsProvider(MetricsProvider):
    """Default in-memory provider (existing behavior)."""
    
    def __init__(self):
        self.metrics: Dict[str, Any] = defaultdict(int)
    
    def emit_metric(self, name: str, value: float, metric_type: str = "gauge", 
                   labels: Optional[Dict[str, str]] = None) -> None:
        # Store in-memory (existing behavior)
        pass
    
    def flush(self) -> None:
        pass
```

#### 2.2 Enhance ConnectorObservability
**File:** `src/glean/indexing/observability/observability.py`

- [ ] Add optional `metrics_provider` parameter to `__init__`
- [ ] Default to `InMemoryMetricsProvider()` if not provided
- [ ] Update metric recording methods to also emit via provider
- [ ] Add `flush()` method to flush provider metrics
- [ ] Call `flush()` in `end_execution()`

```python
class ConnectorObservability:
    def __init__(
        self,
        connector_name: str,
        metrics_provider: Optional[MetricsProvider] = None,
        datasource: Optional[str] = None,
        crawl_mode: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.connector_name = connector_name
        self.datasource = datasource
        self.crawl_mode = crawl_mode
        self.run_id = run_id or str(uuid.uuid4())
        self.metrics_provider = metrics_provider or InMemoryMetricsProvider()
        # ... existing code
```

#### 2.3 Implement P0 Metrics Emission
**File:** `src/glean/indexing/observability/observability.py`

Add methods to emit standard metrics:
- [ ] `record_upload_batch_size(batch_size: int)`
- [ ] `record_upload_throughput(docs_per_sec: float)`
- [ ] `record_api_request_latency(latency_ms: float, endpoint: str)`
- [ ] `record_api_request_count(endpoint: str)`
- [ ] `record_api_request_error(endpoint: str, error_type: str)`
- [ ] `record_retry(operation: str)`
- [ ] `record_crawl_success()`
- [ ] `record_crawl_failure(error_type: str)`

Each should emit via `self.metrics_provider.emit_metric()` with appropriate labels.

#### 2.4 GCP Cloud Provider (Optional)
**File:** `src/glean/indexing/observability/cloud/gcp.py` (new)

```python
"""GCP Cloud Logging and Monitoring integration.

Requires: pip install glean-indexing-sdk[gcp]
"""

try:
    from google.cloud import logging as gcp_logging
    from google.cloud import monitoring_v3
    HAS_GCP = True
except ImportError:
    HAS_GCP = False


class GCPMetricsProvider(MetricsProvider):
    """Google Cloud Monitoring metrics provider."""
    
    def __init__(self, project_id: str, credentials=None):
        if not HAS_GCP:
            raise ImportError(
                "GCP dependencies not installed. "
                "Install with: pip install glean-indexing-sdk[gcp]"
            )
        # Lazy init of GCP client
        self.client = monitoring_v3.MetricServiceClient(credentials=credentials)
        self.project_id = project_id
        self.project_name = f"projects/{project_id}"
    
    def emit_metric(self, name: str, value: float, ...):
        # Implementation
        pass


def add_gcp_logging_handler(
    logger: logging.Logger,
    project_id: str,
    credentials=None,
    log_name: str = "glean-connector",
) -> logging.Handler:
    """Add GCP Cloud Logging handler to a logger."""
    if not HAS_GCP:
        raise ImportError("...")
    
    # Lazy init
    client = gcp_logging.Client(project=project_id, credentials=credentials)
    handler = client.get_default_handler()
    logger.addHandler(handler)
    return handler
```

#### 2.5 AWS Cloud Provider (Optional)
**File:** `src/glean/indexing/observability/cloud/aws.py` (new)

Similar structure to GCP but using:
- `boto3` for CloudWatch
- `watchtower` for CloudWatch Logs handler

#### 2.6 Package Dependencies
**File:** `pyproject.toml` or `setup.py`

```toml
[project.optional-dependencies]
gcp = [
    "google-cloud-logging>=3.0.0",
    "google-cloud-monitoring>=2.0.0",
]
aws = [
    "boto3>=1.26.0",
    "watchtower>=3.0.0",
]
```

#### 2.7 Testing
**Files:**
- `tests/unit_tests/observability/test_providers.py` (new)
- `tests/unit_tests/observability/test_metrics_integration.py` (new)
- `tests/unit_tests/observability/cloud/test_gcp.py` (new, mocked)
- `tests/unit_tests/observability/cloud/test_aws.py` (new, mocked)

Tests:
- [ ] Test MetricsProvider interface
- [ ] Test InMemoryMetricsProvider
- [ ] Test ConnectorObservability integration with custom provider
- [ ] Test P0 metrics emission at lifecycle points
- [ ] Test GCP provider with mocked GCP clients
- [ ] Test AWS provider with mocked boto3
- [ ] Test lazy import behavior (no import errors without extras)
- [ ] Test that base SDK works without cloud extras installed

#### 2.8 Documentation
- [ ] Document MetricsProvider interface for custom implementations
- [ ] Add examples for using GCP/AWS providers
- [ ] Document all P0 metrics (name, type, when emitted, labels)
- [ ] Add cookbook example showing custom metrics provider

---

## Testing Strategy

### Unit Tests
- Formatters (✅ complete)
- Lifecycle logging events
- MetricsProvider implementations
- Cloud provider helpers (mocked)

### Integration Tests
- End-to-end connector run with structured logging
- End-to-end connector run with metrics provider
- Verify metrics are emitted at correct lifecycle points
- Verify backwards compatibility (no config = works as before)

### Import Tests
- Verify base SDK imports cleanly without extras
- Verify GCP extras enable GCP features
- Verify AWS extras enable AWS features

---

## Success Criteria

### PR 1: Logging
- [x] StructuredFormatter implemented and tested
- [ ] Lifecycle events emit structured logs with common fields
- [ ] run_id auto-generation works
- [ ] Backwards compatible (existing connectors work unchanged)
- [ ] Documentation with examples

### PR 2: Metrics
- [ ] MetricsProvider interface is extensible
- [ ] P0 metrics auto-emit from SDK lifecycle
- [ ] InMemoryMetricsProvider is zero-config default
- [ ] GCP/AWS providers work when extras installed
- [ ] Lazy imports keep base SDK lightweight
- [ ] Connector authors can implement custom providers

---

## Non-Goals (Out of Scope)

As per design doc:
- ❌ Full OpenTelemetry tracing
- ❌ Dashboards, alerting, visualization
- ❌ P1 metrics (checkpoint, auth refresh) - deferred to other workstreams
- ❌ Required provider wiring for connector authors
- ❌ New connector class hierarchies

---

## Notes

### Extensibility Requirements
Per team feedback, the implementation must allow SDK users to:
1. Implement custom MetricsProvider for their platform (e.g., DataDog, Prometheus)
2. Implement custom logging handlers/formatters as needed
3. Use their company's observability platform via MetricsProvider interface

### Cloud Support
Per instructions, cloud provider implementations (GCP/AWS) are included but:
- Must be optional (via extras)
- Must use lazy imports
- Must not impact base SDK import time
- Team may pick up cloud-specific improvements separately

### Branch Strategy
- All PRs target: `feature/v0-workstream`
- PR format follows: https://github.com/gleanwork/glean-indexing-sdk/pull/27
- Use `[feature][observability]` prefix in PR titles