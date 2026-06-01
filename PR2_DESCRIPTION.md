# [feature][observability] Add metrics provider system

**Base branch:** `feature/v0-workstream`

## Problem

The SDK lacks a standardized way to emit metrics to observability platforms. Connector authors need to:
- Manually integrate with their metrics platform
- Write custom code for each metric type
- Lack consistent metric names and labels across connectors
- Cannot easily switch between observability platforms

## Solution

This PR implements phase 2 of SDK observability improvements - an extensible metrics provider system:

### MetricsProvider Interface
- Abstract `MetricsProvider` interface for platform-agnostic metrics emission
- `MetricType` enum (GAUGE, COUNTER, HISTOGRAM) for semantic metric types
- Allows SDK users to implement custom providers for any platform (DataDog, Prometheus, CloudWatch, etc.)

### InMemoryMetricsProvider
- Zero-config default provider that stores metrics in memory
- Maintains backward compatibility with existing `ConnectorObservability` behavior
- Useful for testing and development

### Enhanced ConnectorObservability
Added `metrics_provider` parameter (optional, defaults to `InMemoryMetricsProvider()`):
```python
obs = ConnectorObservability(
    connector_name="my_connector",
    metrics_provider=custom_provider  # Optional
)
```

### P0 Metrics Methods
Added standardized methods that automatically emit metrics with consistent labels:
- `record_upload_batch_size(batch_size)` - Histogram of batch sizes
- `record_upload_throughput(docs_per_sec)` - Gauge of upload rate
- `record_api_request_latency(latency_ms, endpoint)` - Histogram of API latencies
- `record_api_request_count(endpoint)` - Counter of API requests
- `record_api_request_error(endpoint, error_type)` - Counter of API errors
- `record_retry(operation)` - Counter of retry attempts
- `record_crawl_success()` - Counter of successful crawls
- `record_crawl_failure(error_type)` - Counter of failed crawls

All metrics include consistent labels: `connector`, `datasource`, and context-specific labels like `endpoint`, `error_type`, `crawl_mode`.

### Extensibility
The `MetricsProvider` ABC allows teams to implement cloud-specific plugins:
```python
from glean.indexing.observability import MetricsProvider, MetricType

class DataDogMetricsProvider(MetricsProvider):
    def __init__(self, api_key: str):
        from datadog import initialize, statsd
        initialize(api_key=api_key)
        self.statsd = statsd

    def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
        tags = [f"{k}:{v}" for k, v in (labels or {}).items()]
        if metric_type == MetricType.COUNTER:
            self.statsd.increment(name, value, tags=tags)
        elif metric_type == MetricType.GAUGE:
            self.statsd.gauge(name, value, tags=tags)
        elif metric_type == MetricType.HISTOGRAM:
            self.statsd.histogram(name, value, tags=tags)

    def flush(self):
        pass

# Usage
provider = DataDogMetricsProvider(api_key="your-key")
obs = ConnectorObservability("my_connector", metrics_provider=provider)
obs.record_upload_batch_size(100)  # Automatically emitted to DataDog
```

See `src/glean/indexing/observability/providers.py` for Prometheus example.

## Test Plan

```bash
# Activate Python 3.10+ environment
source .venv310/bin/activate

# Run all observability tests
pytest tests/unit_tests/observability/ -v

# Expected: 80 tests pass
# - 16 tests for formatters (from PR 1)
# - 22 tests for lifecycle logging (from PR 1)
# - 13 tests for setup_connector_logging (from PR 1)
# - 13 tests for metrics providers
# - 16 tests for metrics integration
```

### Test Coverage
- ✅ MetricsProvider interface extensibility
- ✅ InMemoryMetricsProvider gauge/counter/histogram semantics
- ✅ Custom provider implementation
- ✅ P0 metrics emission with correct labels
- ✅ Metrics provider integration with ConnectorObservability
- ✅ flush() called at end_execution()
- ✅ Backward compatibility - existing code works unchanged
- ✅ Metrics dict and MetricsProvider are independent

## Usage Example

**Zero-config (default):**
```python
from glean.indexing.observability import ConnectorObservability

obs = ConnectorObservability("my_connector")
obs.start_execution()
obs.record_upload_batch_size(100)
obs.record_api_request_count("/api/documents")
obs.end_execution()

# Metrics stored in memory
metrics = obs.metrics_provider.get_metrics()
print(metrics)  # {'upload_batch_size': 100.0, 'api_request_count': 1.0}
```

**With custom provider:**
```python
from glean.indexing.observability import ConnectorObservability
from my_company.observability import MyMetricsProvider

provider = MyMetricsProvider(config=my_config)
obs = ConnectorObservability("my_connector", metrics_provider=provider)

obs.start_execution()
obs.record_upload_batch_size(100)  # Emitted to your platform
obs.record_api_request_latency(150.5, "/api/users")  # With labels
obs.end_execution()
```

## Backward Compatibility

100% backward compatible:
- Default `InMemoryMetricsProvider` maintains existing behavior
- `metrics_provider` parameter is optional
- Existing `record_metric()` and `get_metrics_summary()` work unchanged
- Metrics dict and MetricsProvider operate independently
- No breaking changes to public APIs

## Files Changed

- `src/glean/indexing/observability/__init__.py` - Export new providers
- `src/glean/indexing/observability/observability.py` - Add metrics_provider parameter and P0 metrics methods
- `src/glean/indexing/observability/providers.py` - **NEW** (147 lines) - MetricsProvider interface
- `tests/unit_tests/observability/test_providers.py` - **NEW** (126 lines) - Provider tests
- `tests/unit_tests/observability/test_metrics_integration.py` - **NEW** (186 lines) - Integration tests

## Design Decisions

### Why ABC interface instead of concrete implementations?
The team will implement cloud-specific plugins (GCP, AWS) separately. The ABC provides the contract for extensibility without coupling the SDK to specific platforms.

### Why InMemoryMetricsProvider as default?
Zero-config experience - SDK works out-of-the-box without requiring external dependencies or configuration. Users can opt-in to cloud providers when ready.

### Why separate from ConnectorMetrics?
`ConnectorMetrics` (existing) is for ad-hoc user metrics. `ConnectorObservability` (this PR) is for SDK lifecycle metrics. Both coexist for backward compatibility.

## Next Steps

After this PR merges, teams can implement cloud-specific providers as separate modules:
- `glean-indexing-sdk-gcp` package with `GCPMetricsProvider`
- `glean-indexing-sdk-aws` package with `CloudWatchMetricsProvider`
- Custom providers for company-specific platforms
