#!/usr/bin/env python
"""Example usage of the datasource connector."""

import logging
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from glean.connector_sdk.connector import MyDatasourceConnector
from glean.connector_sdk.models import IndexingMode
from glean.connector_sdk.utils import ConnectorMetrics


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Run the datasource connector example."""
    # Create a connector instance
    connector = MyDatasourceConnector()
    
    # Use the ConnectorMetrics context manager to track performance
    with ConnectorMetrics("datasource_example") as metrics:
        # Run the connector
        connector.index_data(mode=IndexingMode.FULL)
        
        # For demonstration, record a custom metric
        metrics.record("connector_name", connector.name)
    
    logger.info("Example completed successfully")


if __name__ == "__main__":
    main() 