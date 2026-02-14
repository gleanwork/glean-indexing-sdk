"""Simple Glean API client helper for connectors."""

import os

from glean.api_client import Glean

from glean.indexing.exceptions import MissingEnvironmentVariableError


def api_client() -> Glean:
    """Get the Glean API client."""
    instance = os.getenv("GLEAN_INSTANCE")
    api_token = os.getenv("GLEAN_INDEXING_API_TOKEN")

    missing = []
    if not api_token:
        missing.append("GLEAN_INDEXING_API_TOKEN")
    if not instance:
        missing.append("GLEAN_INSTANCE")
    if missing:
        raise MissingEnvironmentVariableError(missing)

    return Glean(api_token=api_token, instance=instance)
