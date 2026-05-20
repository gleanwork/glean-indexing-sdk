import os

from glean.indexing.models import IndexingMode

from .webex_connector import WebexConnector
from .webex_data_client import WebexDataClient


mode = IndexingMode(os.environ.get("GLEAN_INDEXING_MODE", IndexingMode.FULL.value))
data_client = WebexDataClient.from_env()
connector = WebexConnector(name="webex", data_client=data_client)

connector.configure_datasource()
connector.sync_identities()
connector.index_data(mode=mode)
data_client.close()
