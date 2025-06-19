from glean.indexing.models import IndexingMode

from .wiki_connector import CompanyWikiConnector
from .wiki_data_client import WikiDataClient

# Initialize
data_client = WikiDataClient(wiki_base_url="https://wiki.company.com", api_token="your-wiki-token")
connector = CompanyWikiConnector(name="company_wiki", data_client=data_client)

# Configure the datasource in Glean
connector.configure_datasource()

# Index all documents
connector.index_data(mode=IndexingMode.FULL)
