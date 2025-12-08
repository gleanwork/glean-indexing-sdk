"""Main entry point for running the wiki connector."""

import logging
import os

from dotenv import load_dotenv

from glean.indexing.models import IndexingMode
from wiki_connector.connector import CompanyWikiConnector
from wiki_connector.data_client import WikiDataClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the wiki connector."""
    # Load environment variables from .env file
    load_dotenv()

    # Validate required environment variables
    wiki_url = os.getenv("WIKI_BASE_URL", "https://wiki.company.com")
    wiki_token = os.getenv("WIKI_API_TOKEN", "example-token")

    logger.info("Initializing wiki connector...")

    # Create the data client
    data_client = WikiDataClient(
        wiki_base_url=wiki_url,
        api_token=wiki_token,
    )

    # Create the connector
    connector = CompanyWikiConnector(
        name="company_wiki",
        data_client=data_client,
    )

    # Configure the datasource in Glean
    # This should be run at least once, and whenever the schema changes
    logger.info("Configuring datasource...")
    connector.configure_datasource()

    # Index all documents (full sync)
    logger.info("Starting full index...")
    connector.index_data(mode=IndexingMode.FULL)

    logger.info("Indexing complete!")


if __name__ == "__main__":
    main()
