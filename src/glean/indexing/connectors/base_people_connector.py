"""Base people connector for the Glean Connector SDK."""

import logging
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import EmployeeInfoDefinition
from glean.indexing.common import api_client
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode, TSourceData
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.push.options import push_options_from_connector_options
from glean.indexing.push.uploader import PushUploader

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
            self._batch_index_employees(employees, options=options)
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

    def _batch_index_employees(
        self,
        employees: Sequence[EmployeeInfoDefinition],
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Index employees to Glean in batches.

        Args:
            employees: The employees to index
            options: Optional connector options for controlling indexing behavior
        """
        if not employees:
            return

        try:
            result = PushUploader(api_client).upload_employees(
                employees=employees,
                batch_size=self.batch_size,
                options=push_options_from_connector_options(options),
            )
            self._observability.increment_counter("batches_uploaded", result.batch_count)
        except Exception as e:
            logger.error(f"Failed to upload employees: {e}")
            self._observability.increment_counter("batch_upload_errors")
            raise

    def index_employees(
        self,
        employees: Sequence[EmployeeInfoDefinition],
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Incrementally index employees through the people `index` endpoint."""
        PushUploader(api_client).index_employees(
            employees=employees,
            options=push_options_from_connector_options(options),
        )

    def delete_employee(
        self,
        *,
        employee_email: str,
        options: Optional[ConnectorOptions] = None,
        version: Optional[int] = None,
    ) -> None:
        """Delete an employee by email."""
        PushUploader(api_client).delete_employee(
            employee_email=employee_email,
            version=version,
            options=push_options_from_connector_options(options),
        )

    def _get_last_crawl_timestamp(self) -> Optional[str]:
        """
        Get the timestamp of the last successful crawl for incremental indexing.

        Subclasses should override this to implement proper timestamp tracking.

        Returns:
            ISO timestamp string or None for full crawl
        """
        return None
