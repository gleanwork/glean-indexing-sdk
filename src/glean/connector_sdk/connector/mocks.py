"""Mock Glean client for testing."""

import logging
from typing import List

from glean.connector_sdk.models import DocumentDefinition, EmployeeDefinition


logger = logging.getLogger(__name__)


class MockGleanClient:
    """Mock Glean API client for examples and testing."""

    def batch_index_documents(
        self, datasource: str, documents: List[DocumentDefinition]
    ) -> None:
        """Mock method for indexing documents."""
        logger.info(
            f"Mock indexing {len(documents)} documents to datasource '{datasource}'"
        )

    def bulk_index_employees(self, employees: List[EmployeeDefinition]) -> None:
        """Mock method for indexing employees."""
        logger.info(f"Mock indexing {len(employees)} employees") 