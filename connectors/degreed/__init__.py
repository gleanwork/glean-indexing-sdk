"""Degreed connector package."""

from connectors.degreed.connector import (
    DegreedConnector,
    DegreedContentDataClient,
    DegreedCrawlError,
)

__all__ = [
    "DegreedConnector",
    "DegreedContentDataClient",
    "DegreedCrawlError",
]
