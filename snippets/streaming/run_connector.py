import os

from glean.indexing.models import IndexingMode

from .article_connector import KnowledgeBaseConnector
from .article_data_client import LargeKnowledgeBaseClient

data_client = LargeKnowledgeBaseClient(
    kb_api_url="https://kb-api.company.com",
    api_key=os.environ["SOURCE_API_TOKEN"],
)
connector = KnowledgeBaseConnector(
    name="knowledgebase",
    data_client=data_client,
)

connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
