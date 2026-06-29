"""AWS cloud plugins for observability."""

import warnings

__all__ = []

try:
    from glean.indexing.plugins.aws.cloudwatch_logs import CloudWatchLogsProvider

    __all__.append("CloudWatchLogsProvider")
except ImportError as e:
    warnings.warn(
        f"CloudWatch Logs provider unavailable. Install with: uv add glean-indexing-sdk[aws]\n"
        f"Error: {e}",
        UserWarning,
        stacklevel=2,
    )

try:
    from glean.indexing.plugins.aws.cloudwatch_metrics import CloudWatchMetricsProvider

    __all__.append("CloudWatchMetricsProvider")
except ImportError as e:
    warnings.warn(
        f"CloudWatch Metrics provider unavailable. Install with: uv add glean-indexing-sdk[aws]\n"
        f"Error: {e}",
        UserWarning,
        stacklevel=2,
    )
