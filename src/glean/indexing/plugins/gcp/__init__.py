"""GCP cloud plugins for observability."""

try:
    from glean.indexing.plugins.gcp.cloud_logging import CloudLoggingProvider
    from glean.indexing.plugins.gcp.cloud_monitoring import CloudMonitoringProvider

    __all__ = [
        "CloudLoggingProvider",
        "CloudMonitoringProvider",
    ]
except ImportError as e:
    import warnings

    warnings.warn(
        f"GCP cloud plugins require optional dependencies. "
        f"Install with: uv add glean-indexing-sdk[gcp]\n"
        f"Error: {e}",
        ImportWarning,
    )
    __all__ = []
