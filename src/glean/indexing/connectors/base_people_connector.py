"""Base people connector for the Glean Connector SDK."""

import logging
import uuid
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import EmployeeInfoDefinition
from glean.indexing.clients.glean_client import api_client
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseConnectorDataClient
from glean.indexing.models import IndexingMode, TSourceData
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.utils import BatchProcessor

logger = logging.getLogger(__name__)


class BasePeopleConnector(BaseConnector[TSourceData, EmployeeInfoDefinition], ABC):
    """
    Base class for people connectors with dependency injection.

    Type Parameters:
        TSourceData: The type of raw employee data from your external source
        EmployeeInfoDefinition: Glean employee model (fixed for people connectors)
    """

    def __init__(self, name: str, data_client: BaseConnectorDataClient[TSourceData]):
        """
        Initialize the people connector.

        Args:
            name: The name of the connector
            data_client: The data client for fetching source data
        """
        super().__init__(name)
        self.data_client = data_client
        self._observability = ConnectorObservability(name)
        self.batch_size = 1000

    @property
    def observability(self) -> ConnectorObservability:
        """The observability instance for this connector."""
        return self._observability

    def index_data(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """Index people data to Glean.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
        """
        self._observability.start_execution()

        try:
            logger.info(f"Starting {mode.name.lower()} people indexing for '{self.name}'")

            since = None
            if mode == IndexingMode.INCREMENTAL:
                since = self._get_last_crawl_timestamp()
                logger.info(f"Incremental crawl since: {since}")

            self._observability.start_timer("data_fetch")
            data = self.get_data(since=since)
            self._observability.end_timer("data_fetch")

            logger.info(f"Retrieved {len(data)} people from source")
            self._observability.record_metric("people_fetched", len(data))

            self._observability.start_timer("data_transform")
            employees = self.transform(data)
            self._observability.end_timer("data_transform")

            logger.info(f"Transformed {len(employees)} employees")
            self._observability.record_metric("employees_transformed", len(employees))

            self._observability.start_timer("data_upload")
            self._batch_index_employees(employees)
            self._observability.end_timer("data_upload")

            logger.info(f"Successfully indexed {len(employees)} employees to Glean")
            self._observability.record_metric("employees_indexed", len(employees))

        except Exception as e:
            logger.exception(f"Error during people indexing: {e}")
            self._observability.increment_counter("indexing_errors")
            raise
        finally:
            self._observability.end_execution()

    def get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """Get data from the data client.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of source data items from the external system.
        """
        return self.data_client.get_source_data(since=since)

    def _batch_index_employees(self, employees: Sequence[EmployeeInfoDefinition]) -> None:
        """Index employees to Glean in batches."""
        if not employees:
            return

        batches = list(BatchProcessor(list(employees), batch_size=self.batch_size))
        total_batches = len(batches)

        logger.info(f"Uploading {len(employees)} employees in {total_batches} batches")

        upload_id = str(uuid.uuid4())
        for i, batch in enumerate(batches):
            try:
                with api_client() as client:
                    client.indexing.people.bulk_index(
                        employees=list(batch),
                        upload_id=upload_id,
                        is_first_page=(i == 0),
                        is_last_page=(i == total_batches - 1),
                    )

                logger.info(f"Employee batch {i + 1}/{total_batches} uploaded successfully")
                self._observability.increment_counter("batches_uploaded")

            except Exception as e:
                logger.error(f"Failed to upload employee batch {i + 1}/{total_batches}: {e}")
                self._observability.increment_counter("batch_upload_errors")
                raise

    def _get_last_crawl_timestamp(self) -> Optional[str]:
        """
        Get the timestamp of the last successful crawl for incremental indexing.

        Subclasses should override this to implement proper timestamp tracking.

        Returns:
            ISO timestamp string or None for full crawl
        """
        return None
