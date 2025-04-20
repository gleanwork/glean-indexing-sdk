"""Response validator for testing connector outputs."""

import logging
from typing import List, Optional

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition

logger = logging.getLogger(__name__)


class ResponseValidator:
    """Validator for connector responses."""

    def __init__(self):
        """Initialize the ResponseValidator."""
        self.documents_posted: List[DocumentDefinition] = []
        self.employees_posted: List[EmployeeInfoDefinition] = []

    def assert_documents_posted(self, count: Optional[int] = None) -> None:
        """Assert that documents were posted.

        Args:
            count: Optional expected count of documents.
        """
        if count is not None:
            assert len(self.documents_posted) == count, (
                f"Expected {count} documents to be posted, but got {len(self.documents_posted)}"
            )
        else:
            assert len(self.documents_posted) > 0, "No documents were posted"

        logger.info(f"Validated {len(self.documents_posted)} documents posted")

    def assert_employees_posted(self, count: Optional[int] = None) -> None:
        """Assert that employees were posted.

        Args:
            count: Optional expected count of employees.
        """
        if count is not None:
            assert len(self.employees_posted) == count, (
                f"Expected {count} employees to be posted, but got {len(self.employees_posted)}"
            )
        else:
            assert len(self.employees_posted) > 0, "No employees were posted"

        logger.info(f"Validated {len(self.employees_posted)} employees posted")

    def reset(self) -> None:
        """Reset the validator state."""
        self.documents_posted.clear()
        self.employees_posted.clear()
