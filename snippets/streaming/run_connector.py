from glean.indexing.models import IndexingMode

from .article_connector import KnowledgeBaseConnector
from .article_data_client import LargeKnowledgeBaseClient

data_client = LargeKnowledgeBaseClient(
    kb_api_url="https://kb-api.company.com", api_key="your-kb-api-key"
)
connector = KnowledgeBaseConnector(name="knowledge_base", data_client=data_client)

connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
