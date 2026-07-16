"""Run a full Degreed-to-Glean catalog crawl."""

from glean.indexing.models import ConnectorOptions
from glean.indexing.observability import ConsoleLoggerProvider, setup_connector_logging

from connectors.degreed import DegreedConnector


def main() -> None:
    """Configure the datasource and run an authoritative full crawl."""
    setup_connector_logging("degreed", logger_provider=ConsoleLoggerProvider())
    connector = DegreedConnector.from_env()
    connector.configure_datasource()
    connector.index_data(options=ConnectorOptions(force_restart=True))


if __name__ == "__main__":
    main()
