from typing import Sequence

from glean.indexing.connectors.base_data_client import BaseConnectorDataClient

from .wiki_page_data import WikiPageData


class WikiDataClient(BaseConnectorDataClient[WikiPageData]):
    """Fetches data from your external system."""

    def __init__(self, wiki_base_url: str, api_token: str):
        self.wiki_base_url = wiki_base_url
        self.api_token = api_token

    def get_source_data(self, since=None) -> Sequence[WikiPageData]:
        """Fetch all your documents here."""
        # Your implementation here - call APIs, read files, query databases
        pass
