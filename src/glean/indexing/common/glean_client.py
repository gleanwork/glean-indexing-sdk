"""Simple Glean API client helper for connectors."""

import os

from glean.api_client import Glean
from glean.indexing.exceptions import MissingEnvironmentVariableError

DEFAULT_TIMEOUT_MS = 60_000


def api_client() -> Glean:
    """Get the Glean API client."""
    server_url = os.getenv("GLEAN_SERVER_URL")
    instance = os.getenv("GLEAN_INSTANCE")  # Deprecated: use GLEAN_SERVER_URL instead
    api_token = os.getenv("GLEAN_INDEXING_API_TOKEN")

    missing = []
    if not api_token:
        missing.append("GLEAN_INDEXING_API_TOKEN")
    if not server_url and not instance:
        missing.append("GLEAN_SERVER_URL")
    if missing:
        raise MissingEnvironmentVariableError(missing)

    if server_url:
        return Glean(api_token=api_token, server_url=server_url, timeout_ms=DEFAULT_TIMEOUT_MS)
    return Glean(api_token=api_token, instance=instance, timeout_ms=DEFAULT_TIMEOUT_MS)
