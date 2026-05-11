"""Mock Glean API client for testing."""

import logging
from typing import Any, Dict, List, Optional

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition

from glean.indexing.testing.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


class _MockDocumentsClient:
    """Mock client for document indexing APIs."""

    def __init__(self, validator: ResponseValidator):
        self.validator = validator

    def bulk_index(
        self,
        datasource: str,
        documents: List[DocumentDefinition],
        upload_id: Optional[str] = None,
        is_first_page: bool = True,
        is_last_page: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Mock bulk document indexing."""
        logger.info(f"Mock indexing {len(documents)} documents to datasource '{datasource}'")
        self.validator.documents_posted.extend(documents)
        return {
            "status": "success",
            "indexed": len(documents),
            "upload_id": upload_id,
            "is_first_page": is_first_page,
            "is_last_page": is_last_page,
        }


class _MockPeopleClient:
    """Mock client for people indexing APIs."""

    def __init__(self, validator: ResponseValidator):
        self.validator = validator

    def bulk_index(
        self,
        employees: List[EmployeeInfoDefinition],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Mock bulk employee indexing."""
        logger.info(f"Mock indexing {len(employees)} employees")
        self.validator.employees_posted.extend(employees)
        return {"status": "success", "indexed": len(employees)}


class _MockPermissionsClient:
    """Mock client for datasource identity indexing APIs."""

    def __init__(self, validator: ResponseValidator):
        self.validator = validator

    def bulk_index_users(self, users: List[Any], **kwargs: Any) -> Dict[str, Any]:
        """Mock bulk user indexing."""
        logger.info(f"Mock indexing {len(users)} users")
        return {"status": "success", "indexed": len(users)}

    def bulk_index_groups(self, groups: List[Any], **kwargs: Any) -> Dict[str, Any]:
        """Mock bulk group indexing."""
        logger.info(f"Mock indexing {len(groups)} groups")
        return {"status": "success", "indexed": len(groups)}

    def bulk_index_memberships(self, memberships: List[Any], **kwargs: Any) -> Dict[str, Any]:
        """Mock bulk membership indexing."""
        logger.info(f"Mock indexing {len(memberships)} memberships")
        return {"status": "success", "indexed": len(memberships)}


class _MockIndexingClient:
    """Mock client for the generated client's indexing namespace."""

    def __init__(self, validator: ResponseValidator):
        self.documents = _MockDocumentsClient(validator)
        self.people = _MockPeopleClient(validator)
        self.permissions = _MockPermissionsClient(validator)


class MockGleanClient:
    """Mock Glean API client for testing that matches the new GleanClient interface."""

    def __init__(self, validator: ResponseValidator):
        """Initialize the MockGleanClient.

        Args:
            validator: Validator to record posted items.
        """
        self.validator = validator
        self.indexing = _MockIndexingClient(validator)

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
        return self.indexing.documents.bulk_index(
            datasource=datasource,
            documents=documents,
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            **kwargs,
        )

    def index_employees(self, employees: List[EmployeeInfoDefinition], **kwargs) -> Dict[str, Any]:
        """Mock method for indexing employees (new interface).

        Args:
            employees: The employees to index.
            **kwargs: Additional parameters

        Returns:
            Mock API response
        """
        return self.indexing.people.bulk_index(employees=employees, **kwargs)

    def batch_index_documents(self, datasource: str, documents: List[DocumentDefinition]) -> None:
        """Legacy method for indexing documents."""
        self.index_documents(datasource=datasource, documents=documents)

    def bulk_index_employees(self, employees: List[EmployeeInfoDefinition]) -> None:
        """Legacy method for indexing employees."""
        self.index_employees(employees=employees)
