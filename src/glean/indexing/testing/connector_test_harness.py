"""Test harness for running and validating connectors."""

import logging
from unittest.mock import patch

from glean.indexing.connectors import BaseConnector, BaseDatasourceConnector, BasePeopleConnector
from glean.indexing.testing.mock_glean_client import MockGleanClient
from glean.indexing.testing.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


class ConnectorTestHarness:
    """Test harness for connectors that works with the new dependency injection pattern."""

    def __init__(self, connector: BaseConnector):
        """Initialize the ConnectorTestHarness.

        Args:
            connector: The connector to test.
        """
        self.connector = connector
        self.validator = ResponseValidator()
        self.mock_client = MockGleanClient(self.validator)

    def run(self) -> None:
        """Run the connector."""
        logger.info(f"Running test harness for connector '{self.connector.name}'")

        # Reset validator
        self.validator.reset()

        # Patch the api_client to return our mock client
        with (
            patch(
                "glean.indexing.connectors.base_datasource_connector.api_client"
            ) as mock_api_client,
            patch(
                "glean.indexing.connectors.base_people_connector.api_client"
            ) as mock_people_api_client,
        ):
            mock_api_client.return_value.__enter__.return_value = self.mock_client
            mock_people_api_client.return_value.__enter__.return_value = self.mock_client

            # Run the connector for any supported type
            if isinstance(self.connector, (BaseDatasourceConnector, BasePeopleConnector)):
                self.connector.index_data()
            else:
                raise ValueError(f"Unsupported connector type: {type(self.connector)}")

    def get_validator(self) -> ResponseValidator:
        """Get the response validator for checking results."""
        return self.validator
