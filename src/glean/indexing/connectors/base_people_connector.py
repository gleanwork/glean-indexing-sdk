"""Base people connector for the Glean Connector SDK."""

import logging
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import EmployeeInfoDefinition

from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode, TSourceData
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.push import PushUploader

logger = logging.getLogger(__name__)


class BasePeopleConnector(BaseConnector[TSourceData, EmployeeInfoDefinition], ABC):
    """
    Base class for all Glean people connectors.

    This class provides the core logic for indexing people/identity data (users, groups, memberships) from external systems into Glean.
    Subclasses must define a `configuration` attribute of type `CustomDatasourceConfig` describing the people source.

    To implement a custom people connector, inherit from this class and implement:
        - configuration: CustomDatasourceConfig (class or instance attribute)
        - get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]
        - transform(self, data: Sequence[TSourceData]) -> Sequence[EmployeeInfoDefinition]

    Attributes:
        name (str): The unique name of the connector (should be snake_case).
        configuration (CustomDatasourceConfig): The people source configuration for Glean registration.
        batch_size (int): The batch size for uploads (default: 1000).
        data_client (BaseDataClient): The data client for fetching source data.
        observability (ConnectorObservability): Observability and metrics for this connector.

    Example:
        class MyPeopleConnector(BasePeopleConnector[MyEmployeeData]):
            configuration = CustomDatasourceConfig(...)
            ...
    """

    def __init__(self, name: str, data_client: BaseDataClient[TSourceData]):
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

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Index people data to Glean.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            options: Optional connector options for controlling indexing behavior.
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
            if employees:
                force_restart = options.force_restart if options else False
                if force_restart:
                    logger.info("Force restarting upload - discarding any previous upload progress")

                PushUploader(
                    datasource=self.name,
                    timeout_ms=options.upload_timeout_ms if options else None,
                ).bulk_index_employees(
                    employees=employees,
                    batch_size=self.batch_size,
                    force_restart_upload=True if force_restart else None,
                    disable_stale_data_deletion_check=True
                    if (options and options.disable_stale_deletion_check)
                    else None,
                )
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

    def _get_last_crawl_timestamp(self) -> Optional[str]:
        """
        Get the timestamp of the last successful crawl for incremental indexing.

        Subclasses should override this to implement proper timestamp tracking.

        Returns:
            ISO timestamp string or None for full crawl
        """
        return None
