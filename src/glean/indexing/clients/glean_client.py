"""Simple Glean API client helper for connectors."""

import os

from glean.api_client import Glean


def api_client() -> Glean:
    """Get the Glean API client."""
    instance = os.getenv("GLEAN_INSTANCE")
    api_token = os.getenv("GLEAN_INDEXING_API_TOKEN")

    if not api_token or not instance:
        raise ValueError(
            "GLEAN_INDEXING_API_TOKEN and GLEAN_INSTANCE environment variables are required"
        )

    return Glean(api_token=api_token, instance=instance)
