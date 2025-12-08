"""Simple wiki connector example for Glean Indexing SDK."""

from wiki_connector.connector import CompanyWikiConnector
from wiki_connector.data_client import WikiDataClient
from wiki_connector.models import WikiPageData

__all__ = ["CompanyWikiConnector", "WikiDataClient", "WikiPageData"]
