"""Mock data source for testing connectors."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MockDataSource:
    """Mock data source for testing."""

    def __init__(
        self,
        all_items: Optional[List[Dict[str, Any]]] = None,
        modified_items: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize the MockDataSource.

        Args:
            all_items: Items to return for get_all_items.
            modified_items: Items to return for get_modified_items.
        """
        self.all_items = all_items or []
        self.modified_items = modified_items or []

    def get_all_items(self) -> List[Dict[str, Any]]:
        """Get all items.

        Returns:
            A list of all items.
        """
        logger.info(f"MockDataSource.get_all_items() returning {len(self.all_items)} items")
        return self.all_items

    def get_modified_items(self, since: str) -> List[Dict[str, Any]]:
        """Get modified items.

        Args:
            since: Timestamp to filter by.

        Returns:
            A list of modified items.
        """
        logger.info(
            f"MockDataSource.get_modified_items(since={since}) returning {len(self.modified_items)} items"
        )
        return self.modified_items
