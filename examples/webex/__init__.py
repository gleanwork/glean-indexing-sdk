"""Webex connector for the Glean Indexing SDK (example).

Indexes Webex group spaces and their messages into a Glean custom datasource.
Full-crawl only; see ``.glean/connector_plan.md`` for scope and follow-up work.

Two data clients are provided:

* :class:`WebexDataClient` -- room-scoped (bot/user token).
* :class:`WebexEventsDataClient` -- org-wide via the compliance Events API.
"""

from examples.webex.connector import WebexConnector
from examples.webex.data_client import WebexDataClient, WebexEventsDataClient

__all__ = ["WebexConnector", "WebexDataClient", "WebexEventsDataClient"]
