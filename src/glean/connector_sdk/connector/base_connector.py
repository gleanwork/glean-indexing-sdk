"""Base connector class for the Glean Connector SDK."""

import abc
import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
D = TypeVar("D", bound=dict)


class BaseConnector(abc.ABC):
    """Base class for all connectors."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the connector."""
        pass

    def get_client(self) -> Any:
        """Get the Glean API client.

        This method should be implemented by the connector or provided by the application.
        """
        # This would typically be implemented by a concrete connector class
        # or provided by the application. For now, we'll return a mock client.
        from glean.connector_sdk.connector.mocks import MockGleanClient
        return MockGleanClient()
