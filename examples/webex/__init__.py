"""Webex connector for the Glean Indexing SDK (example).

Indexes Webex group spaces and their messages into a Glean custom datasource.
Full-crawl only; see ``.glean/connector_plan.md`` for scope and follow-up work.
"""

from examples.webex.connector import WebexConnector
from examples.webex.data_client import WebexDataClient

__all__ = ["WebexConnector", "WebexDataClient"]
