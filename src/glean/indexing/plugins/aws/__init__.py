"""AWS cloud plugins for observability."""

try:
    from glean.indexing.plugins.aws.cloudwatch_logs import CloudWatchLogsProvider
    from glean.indexing.plugins.aws.cloudwatch_metrics import CloudWatchMetricsProvider

    __all__ = [
        "CloudWatchLogsProvider",
        "CloudWatchMetricsProvider",
    ]
except ImportError as e:
    import warnings

    warnings.warn(
        f"AWS cloud plugins require optional dependencies. "
        f"Install with: uv add glean-indexing-sdk[aws]\n"
        f"Error: {e}",
        ImportWarning,
    )
    __all__ = []
