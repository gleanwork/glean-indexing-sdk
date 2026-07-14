"""Run a full Zulip-to-Glean crawl."""

from glean.indexing.models import ConnectorOptions
from glean.indexing.observability import setup_connector_logging

from connectors.zulip import ZulipConnector


def main() -> None:
    """Configure the datasource and run an authoritative full crawl."""
    setup_connector_logging("zulip")
    connector = ZulipConnector.from_env()
    connector.configure_datasource()
    connector.index_data(options=ConnectorOptions(force_restart=True))


if __name__ == "__main__":
    main()
