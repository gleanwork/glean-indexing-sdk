# [feature][observability] Add structured logging and lifecycle events

**Base branch:** `feature/v0-workstream`

## Problem

The SDK lacks structured logging and standardized lifecycle event emission, making it difficult to:
- Correlate logs across distributed crawl operations
- Integrate with modern observability platforms (DataDog, Splunk, etc.)
- Track crawl lifecycle with consistent context fields
- Debug issues across multiple connector runs

## Solution

This PR implements the first phase of the SDK observability improvements (PR 1 of 2):

### Structured Logging
- Added `StructuredFormatter`: JSON formatter for structured logging compatible with Python's stdlib logging
- Added `CompactStructuredFormatter`: Variant that omits empty/null fields for cleaner logs
- Both formatters support:
  - ISO 8601 timestamps
  - Exception formatting with stack traces
  - Custom field names via `extra={}`
  - Full backward compatibility with existing code

### Enhanced ConnectorObservability
- Added `run_id` field (auto-generated UUID) for correlating events across a crawl
- Added `datasource` and `crawl_mode` fields for additional context
- Added `get_common_fields()` method to ensure consistent correlation fields across all events
- Added `fail_execution(error)` method for structured error tracking

### Lifecycle Event Methods
Added standardized event logging methods that emit structured events with consistent fields:
- `log_data_fetch_started()` / `log_data_fetch_completed()`
- `log_transform_started()` / `log_transform_completed()`
- `log_batch_upload_started()` / `log_batch_upload_completed()` / `log_batch_upload_failed()`

All events include common correlation fields: `connector`, `datasource`, `run_id`, `crawl_mode`, `operation`

### Updated setup_connector_logging()
Enhanced with new optional parameters:
- `use_structured_logging`: Enable JSON structured logging
- `formatter`: Custom formatter override
- `extra_handlers`: Additional logging handlers

Default behavior unchanged - human-readable logging remains the default for backward compatibility.

### Example Usage

**Structured Logging:**
```python
from glean.indexing.observability import setup_connector_logging, ConnectorObservability

# Enable structured JSON logging
setup_connector_logging("my_connector", use_structured_logging=True)

obs = ConnectorObservability(
    connector_name="my_connector",
    datasource="salesforce",
    crawl_mode="incremental"
)

obs.start_execution()
obs.log_data_fetch_started(since="2024-01-01")
obs.log_data_fetch_completed(item_count=150, duration_ms=2500)
obs.end_execution()
```

**Output:**
```json
{"timestamp": "2024-01-15T10:30:00.123Z", "level": "INFO", "message": "Crawl started", "connector": "my_connector", "datasource": "salesforce", "crawl_mode": "incremental", "run_id": "a1b2c3...", "operation": "crawl_started"}
{"timestamp": "2024-01-15T10:30:00.456Z", "level": "INFO", "message": "Data fetch started", "connector": "my_connector", "datasource": "salesforce", "run_id": "a1b2c3...", "operation": "data_fetch_started", "since": "2024-01-01"}
{"timestamp": "2024-01-15T10:30:03.789Z", "level": "INFO", "message": "Data fetch completed: 150 items", "connector": "my_connector", "item_count": 150, "duration_ms": 2500, "status": "success"}
```

## Test Plan

```bash
# Activate Python 3.10+ environment
source .venv310/bin/activate

# Run observability tests
pytest tests/unit_tests/observability/ -v

# Expected: 51 tests pass
# - 16 tests for formatters (StructuredFormatter, CompactStructuredFormatter)
# - 22 tests for lifecycle logging (initialization, events, common fields)
# - 13 tests for setup_connector_logging (structured logging, backward compatibility)
```

### Test Coverage
- ✅ Structured formatters emit valid JSON
- ✅ run_id auto-generation and uniqueness
- ✅ Lifecycle events include all common fields
- ✅ Backward compatibility - existing code works unchanged
- ✅ Custom formatters and extra handlers
- ✅ Integration with Python stdlib logging

## Backward Compatibility

100% backward compatible:
- Structured logging is **opt-in** via `use_structured_logging=True`
- Default behavior unchanged (human-readable logs)
- All existing ConnectorObservability methods work as before
- All existing parameters have defaults
- No breaking changes to public APIs

## Files Changed

- `src/glean/indexing/observability/__init__.py` - Export new formatters
- `src/glean/indexing/observability/formatters.py` - **NEW** (211 lines)
- `src/glean/indexing/observability/observability.py` - Enhanced (+270 lines)
- `tests/unit_tests/observability/__init__.py` - **NEW**
- `tests/unit_tests/observability/test_formatters.py` - **NEW** (415 lines)
- `tests/unit_tests/observability/test_lifecycle_logging.py` - **NEW** (454 lines)
- `tests/unit_tests/observability/test_setup_logging.py` - **NEW** (273 lines)

## Next Steps

This is PR 1 of 2. PR 2 will add the Metrics Provider System for standardized metrics emission.
