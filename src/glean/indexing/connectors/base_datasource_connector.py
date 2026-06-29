"""Base datasource connector for the Glean Connector SDK."""

import logging
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import DocumentDefinition

from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.exceptions import InconsistentDataError, InvalidDatasourceConfigError
from glean.indexing.models import (
    ConnectorOptions,
    CustomDatasourceConfig,
    DatasourceIdentityDefinitions,
    IndexingMode,
    TSourceData,
)
from glean.indexing.observability.observability import ConnectorObservability
from glean.indexing.push import PushUploader

logger = logging.getLogger(__name__)


class BaseDatasourceConnector(BaseConnector[TSourceData, DocumentDefinition], ABC):
    """
    Base class for all Glean datasource connectors.

    This class provides the core logic for indexing document/content data from external systems into Glean.
    Subclasses must define a `configuration` attribute of type `CustomDatasourceConfig` describing the datasource.

    To implement a custom connector, inherit from this class and implement:
        - configuration: CustomDatasourceConfig (class or instance attribute)
        - get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]
        - transform(self, data: Sequence[TSourceData]) -> List[DocumentDefinition]

    Attributes:
        name (str): The unique name of the connector (should be snake_case).
        configuration (CustomDatasourceConfig): The datasource configuration for Glean registration.
        batch_size (int): The batch size for uploads (default: 1000).
        data_client (BaseDataClient): The data client for fetching source data.
        observability (ConnectorObservability): Observability and metrics for this connector.

    Example:
        class MyWikiConnector(BaseDatasourceConnector[WikiPageData]):
            configuration = CustomDatasourceConfig(...)
            ...
    """

    configuration: CustomDatasourceConfig

    def __init__(self, name: str, data_client: BaseDataClient[TSourceData]):
        """
        Initialize the datasource connector.

        Args:
            name: The name of the connector
            data_client: The data client for fetching source data
        """
        super().__init__(name)
        self.data_client = data_client
        self._observability = ConnectorObservability(name)
        self.batch_size = 1000

    @property
    def display_name(self) -> str:
        """Get the display name for this datasource."""
        return self.name.replace("_", " ").title()

    @property
    def observability(self) -> ConnectorObservability:
        """The observability instance for this connector."""
        return self._observability

    def get_identities(self) -> DatasourceIdentityDefinitions:
        """
        Gets all identities for this datasource (users, groups & memberships).

        Returns:
            A DatasourceIdentityDefinitions object containing all identities for this datasource.
        """
        return DatasourceIdentityDefinitions(users=[])

    def get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """Get data from the datasource via the data client.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of source data items from the external system.
        """
        return self.data_client.get_source_data(since=since)

    def configure_datasource(self, is_test: bool = False) -> None:
        """
        Configure the datasource in Glean using the datasources.add() API.

        Args:
            is_test: Whether this is a test datasource
        """
        config = self.configuration

        if not config.name:
            raise InvalidDatasourceConfigError("name")

        if not config.display_name:
            raise InvalidDatasourceConfigError("display_name")

        logger.info(f"Configuring datasource: {config.name}")

        if is_test:
            config.is_test_datasource = True

        PushUploader(datasource=config.name).configure_datasource(config)
        logger.info(f"Successfully configured datasource: {config.name}")

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """
        Index data from the datasource to Glean with identity crawl followed by content crawl.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            options: Optional connector options for controlling indexing behavior.
        """
        self._observability.start_execution()

        try:
            logger.info(f"Starting {mode.name.lower()} indexing for datasource '{self.name}'")

            logger.info("Starting identity crawl")
            identities = self.get_identities()

            users = identities.get("users")
            if users:
                logger.info(f"Indexing {len(users)} users")
                PushUploader(datasource=self.name).bulk_index_users(
                    users=users, batch_size=self.batch_size
                )

            groups = identities.get("groups")
            if groups:
                logger.info(f"Indexing {len(groups)} groups")
                PushUploader(datasource=self.name).bulk_index_groups(
                    groups=groups, batch_size=self.batch_size
                )

                memberships = identities.get("memberships")
                if not memberships:
                    raise InconsistentDataError(
                        "identity data",
                        "Groups were provided, but no memberships were provided",
                        "Implement get_identities() to return both 'groups' and 'memberships' keys, "
                        "or remove groups if memberships are not available",
                    )

                logger.info(f"Indexing {len(memberships)} memberships")
                PushUploader(datasource=self.name).bulk_index_memberships(
                    memberships=memberships, batch_size=self.batch_size
                )

            since = None
            if mode == IndexingMode.INCREMENTAL:
                since = self._get_last_crawl_timestamp()
                logger.info(f"Incremental crawl since: {since}")

            logger.info("Starting content crawl")
            self._observability.start_timer("data_fetch")
            data = self.get_data(since=since)
            self._observability.end_timer("data_fetch")

            logger.info(f"Retrieved {len(data)} items from datasource")
            self._observability.record_metric("items_fetched", len(data))

            self._observability.start_timer("data_transform")
            documents = self.transform(data)
            self._observability.end_timer("data_transform")

            logger.info(f"Transformed {len(documents)} documents")
            self._observability.record_metric("documents_transformed", len(documents))

            self._observability.start_timer("data_upload")
            if documents:
                logger.info(f"Indexing {len(documents)} documents")
                force_restart = options.force_restart if options else False
                if force_restart:
                    logger.info("Force restarting upload - discarding any previous upload progress")

                PushUploader(
                    datasource=self.name,
                    timeout_ms=options.upload_timeout_ms if options else None,
                    observability=self._observability,
                ).bulk_index_documents(
                    documents=documents,
                    batch_size=self.batch_size,
                    force_restart_upload=True if force_restart else None,
                    disable_stale_document_deletion_check=True
                    if (options and options.disable_stale_deletion_check)
                    else None,
                )
            self._observability.end_timer("data_upload")

            logger.info(f"Successfully indexed {len(documents)} documents to Glean")
            self._observability.record_metric("documents_indexed", len(documents))

        except Exception as e:
            logger.exception(f"Error during indexing: {e}")
            self._observability.increment_counter("indexing_errors")
            raise
        finally:
            self._observability.end_execution()

    def _get_last_crawl_timestamp(self) -> Optional[str]:
        """
        Get the timestamp of the last successful crawl for incremental indexing.

        Subclasses should override this to implement proper timestamp tracking.

        Returns:
            ISO timestamp string or None for full crawl
        """
        return None
