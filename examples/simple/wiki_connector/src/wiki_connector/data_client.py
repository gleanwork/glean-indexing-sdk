"""Data client for fetching wiki pages."""

from typing import Optional, Sequence

from glean.indexing.connectors import BaseConnectorDataClient
from wiki_connector.models import WikiPageData


class WikiDataClient(BaseConnectorDataClient[WikiPageData]):
    """Fetches wiki pages from the source system.

    In a real implementation, this would call your wiki's API.
    This example uses static data for demonstration.
    """

    def __init__(self, wiki_base_url: str, api_token: str):
        """Initialize the wiki data client.

        Args:
            wiki_base_url: Base URL of the wiki system.
            api_token: API token for authentication.
        """
        self.wiki_base_url = wiki_base_url
        self.api_token = api_token

    def get_source_data(self, since: Optional[str] = None) -> Sequence[WikiPageData]:
        """Fetch wiki pages from the source system.

        Args:
            since: Optional timestamp for incremental fetches.
                   If provided, only return pages modified after this time.

        Returns:
            Sequence of wiki page data.
        """
        # In a real implementation, you would:
        # 1. Call your wiki's API
        # 2. Handle pagination
        # 3. Filter by 'since' for incremental syncs

        # Example static data for demonstration
        return [
            {
                "id": "page_001",
                "title": "Engineering Onboarding Guide",
                "content": "Welcome to the engineering team! This guide covers...",
                "author": "jane.smith@company.com",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-02-01T14:30:00Z",
                "url": f"{self.wiki_base_url}/pages/001",
                "tags": ["onboarding", "engineering"],
            },
            {
                "id": "page_002",
                "title": "API Documentation Standards",
                "content": "Our standards for API documentation include...",
                "author": "john.doe@company.com",
                "created_at": "2024-01-20T09:15:00Z",
                "updated_at": "2024-01-25T16:45:00Z",
                "url": f"{self.wiki_base_url}/pages/002",
                "tags": ["api", "documentation", "standards"],
            },
            {
                "id": "page_003",
                "title": "Production Deployment Checklist",
                "content": "Before deploying to production, ensure you have...",
                "author": "ops.team@company.com",
                "created_at": "2024-02-01T11:00:00Z",
                "updated_at": "2024-02-10T09:00:00Z",
                "url": f"{self.wiki_base_url}/pages/003",
                "tags": ["deployment", "production", "checklist"],
            },
        ]
