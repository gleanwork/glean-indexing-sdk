"""Mock implementations for testing."""

import logging
from typing import List

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition

logger = logging.getLogger(__name__)


class MockGleanClient:
    """Mock Glean API client for examples and testing."""

    def batch_index_documents(self, datasource: str, documents: List[DocumentDefinition]) -> None:
        """Mock method for indexing documents."""
        logger.info(f"Mock indexing {len(documents)} documents to datasource '{datasource}'")

    def bulk_index_employees(self, employees: List[EmployeeInfoDefinition]) -> None:
        """Mock method for indexing employees."""
        logger.info(f"Mock indexing {len(employees)} employees")
