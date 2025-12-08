"""Main entry point for the containerized connector."""

import argparse
import logging
import sys

from glean.indexing.models import IndexingMode

from connector.sample_connector import SampleConnector, SampleDataClient

# Configure logging for container output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the connector with command-line arguments."""
    parser = argparse.ArgumentParser(description="Glean Indexing Connector")
    parser.add_argument(
        "--mode",
        choices=["FULL", "INCREMENTAL"],
        default="FULL",
        help="Indexing mode (default: FULL)",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        help="Configure datasource before indexing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform data without uploading",
    )

    args = parser.parse_args()

    logger.info(f"Starting connector (mode={args.mode})")

    try:
        # Create data client and connector
        data_client = SampleDataClient()
        connector = SampleConnector(
            name="docker_docs",
            data_client=data_client,
        )

        # Configure datasource if requested
        if args.configure:
            logger.info("Configuring datasource...")
            connector.configure_datasource()

        # Dry run mode - just fetch and transform
        if args.dry_run:
            logger.info("Dry run mode - fetching and transforming data...")
            data = connector.get_data()
            documents = connector.transform(data)
            logger.info(f"Would index {len(documents)} documents")
            for doc in documents:
                logger.info(f"  - {doc.id}: {doc.title}")
            return

        # Execute indexing
        mode = IndexingMode.FULL if args.mode == "FULL" else IndexingMode.INCREMENTAL
        logger.info(f"Starting indexing (mode={mode.name})...")
        connector.index_data(mode=mode)

        logger.info("Indexing completed successfully")

    except Exception as e:
        logger.error(f"Connector failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
