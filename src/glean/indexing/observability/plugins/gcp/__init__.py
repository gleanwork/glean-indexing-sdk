"""GCP cloud plugins for observability."""

import warnings

__all__ = []

try:
    from glean.indexing.plugins.gcp.cloud_logging import CloudLoggingProvider

    __all__.append("CloudLoggingProvider")
except ImportError as e:
    warnings.warn(
        f"Cloud Logging provider unavailable. Install with: uv add glean-indexing-sdk[gcp]\n"
        f"Error: {e}",
        UserWarning,
        stacklevel=2,
    )

try:
    from glean.indexing.plugins.gcp.cloud_monitoring import CloudMonitoringProvider

    __all__.append("CloudMonitoringProvider")
except ImportError as e:
    warnings.warn(
        f"Cloud Monitoring provider unavailable. Install with: uv add glean-indexing-sdk[gcp]\n"
        f"Error: {e}",
        UserWarning,
        stacklevel=2,
    )
