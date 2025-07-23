import logging
from typing import List

logger = logging.getLogger(__name__)


class MockDataSourceClient:
    """Mock API client for a datasource."""

    def get_all_items(self) -> List[dict]:
        return [
            {
                "id": f"doc-{i}",
                "title": f"Document {i}",
                "content": f"This is the content of document {i}",
                "url": f"https://example.com/docs/{i}",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "author": "user@example.com",
                "type": "document",
                "tags": ["example", "documentation"],
            }
            for i in range(1, 6)
        ]

    def get_modified_items(self, since: str) -> List[dict]:
        return [
            {
                "id": "doc-3",
                "title": "Document 3 (Updated)",
                "content": "This is the updated content of document 3",
                "url": "https://example.com/docs/3",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-03T00:00:00Z",
                "author": "user@example.com",
                "type": "document",
                "tags": ["example", "documentation", "updated"],
            }
        ]


class MockPeopleClient:
    """Mock API client for a people source."""

    def get_all_people(self) -> List[dict]:
        return [
            {
                "id": f"user-{i}",
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "manager_id": None if i == 1 else "user-1",
                "department": "Engineering",
                "title": "Software Engineer",
                "start_date": "2023-01-01",
                "location": "San Francisco, CA",
            }
            for i in range(1, 6)
        ]

    def get_modified_people(self, since: str) -> List[dict]:
        return [
            {
                "id": "user-3",
                "name": "User 3 (Updated)",
                "email": "user3@example.com",
                "manager_id": "user-1",
                "department": "Product",
                "title": "Product Manager",
                "start_date": "2023-01-01",
                "location": "New York, NY",
            }
        ]
