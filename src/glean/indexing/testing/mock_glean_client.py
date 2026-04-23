"""Mock Glean API client for testing."""

import logging
from typing import Any, Dict, List, Optional

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition
from glean.indexing.testing.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


class MockGleanClient:
    """Mock Glean API client for testing that matches the new GleanClient interface."""

    def __init__(self, validator: ResponseValidator):
        """Initialize the MockGleanClient.

        Args:
            validator: Validator to record posted items.
        """
        self.validator = validator

    def index_documents(
        self,
        datasource: str,
        documents: List[DocumentDefinition],
        upload_id: Optional[str] = None,
        is_first_page: bool = True,
        is_last_page: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Mock method for indexing documents (new interface).

        Args:
            datasource: The datasource name.
            documents: The documents to index.
            upload_id: Optional upload ID for batch tracking
            is_first_page: Whether this is the first page of a multi-page upload
            is_last_page: Whether this is the last page of a multi-page upload
            **kwargs: Additional parameters

        Returns:
            Mock API response
        """
        logger.info(f"Mock indexing {len(documents)} documents to datasource '{datasource}'")
        self.validator.documents_posted.extend(documents)
        return {"status": "success", "indexed": len(documents)}

    def index_employees(self, employees: List[EmployeeInfoDefinition], **kwargs) -> Dict[str, Any]:
        """Mock method for indexing employees (new interface).

        Args:
            employees: The employees to index.
            **kwargs: Additional parameters

        Returns:
            Mock API response
        """
        logger.info(f"Mock indexing {len(employees)} employees")
        self.validator.employees_posted.extend(employees)
        return {"status": "success", "indexed": len(employees)}

    def batch_index_documents(self, datasource: str, documents: List[DocumentDefinition]) -> None:
        """Legacy method for indexing documents."""
        self.index_documents(datasource=datasource, documents=documents)

    def bulk_index_employees(self, employees: List[EmployeeInfoDefinition]) -> None:
        """Legacy method for indexing employees."""
        self.index_employees(employees=employees)
