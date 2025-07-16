"""Base datasource connector for the Glean Connector SDK."""

import logging
import uuid
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import DocumentDefinition
from glean.indexing.common import BatchProcessor, api_client
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseConnectorDataClient
from glean.indexing.models import (
    CustomDatasourceConfig,
    DatasourceIdentityDefinitions,
    IndexingMode,
    TSourceData,
)
from glean.indexing.observability.observability import ConnectorObservability

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
        data_client (BaseConnectorDataClient): The data client for fetching source data.
        observability (ConnectorObservability): Observability and metrics for this connector.

    Example:
        class MyWikiConnector(BaseDatasourceConnector[WikiPageData]):
            configuration = CustomDatasourceConfig(...)
            ...
    """

    configuration: CustomDatasourceConfig

    def __init__(self, name: str, data_client: BaseConnectorDataClient[TSourceData]):
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
            raise ValueError("Missing required field: name in Configuration")

        if not config.display_name:
            raise ValueError("Missing required field: display_name in Configuration")

        logger.info(f"Configuring datasource: {config.name}")

        if is_test:
            config.is_test_datasource = True

        with api_client() as client:
            client.indexing.datasources.add(**config.dict(exclude_unset=True))
            logger.info(f"Successfully configured datasource: {config.name}")

    def index_data(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """
        Index data from the datasource to Glean with identity crawl followed by content crawl.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
        """
        self._observability.start_execution()

        try:
            logger.info(f"Starting {mode.name.lower()} indexing for datasource '{self.name}'")

            logger.info("Starting identity crawl")
            identities = self.get_identities()

            users = identities.get("users")
            if users:
                logger.info(f"Indexing {len(users)} users")
                self._batch_index_users(users)

            groups = identities.get("groups")
            if groups:
                # Validate that memberships are provided before indexing groups
                memberships = identities.get("memberships")
                if not memberships:
                    raise ValueError("Groups were provided, but no memberships were provided.")

                logger.info(f"Indexing {len(groups)} groups")
                self._batch_index_groups(groups)

                logger.info(f"Indexing {len(memberships)} memberships")
                self._batch_index_memberships(memberships)

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
                self._batch_index_documents(documents)
            self._observability.end_timer("data_upload")

            logger.info(f"Successfully indexed {len(documents)} documents to Glean")
            self._observability.record_metric("documents_indexed", len(documents))

        except Exception as e:
            logger.exception(f"Error during indexing: {e}")
            self._observability.increment_counter("indexing_errors")
            raise
        finally:
            self._observability.end_execution()

    def _batch_index_users(self, users) -> None:
        """Index users in batches with proper page signaling."""
        if not users:
            return

        batches = list(BatchProcessor(users, batch_size=self.batch_size))
        total_batches = len(batches)

        logger.info(f"Uploading {len(users)} users in {total_batches} batches")

        upload_id = str(uuid.uuid4())
        for i, batch in enumerate(batches):
            try:
                with api_client() as client:
                    client.indexing.permissions.bulk_index_users(
                        datasource=self.name,
                        users=list(batch),
                        upload_id=upload_id,
                        is_first_page=(i == 0),
                        is_last_page=(i == total_batches - 1),
                    )

                logger.info(f"User batch {i + 1}/{total_batches} uploaded successfully")
                self._observability.increment_counter("batches_uploaded")

            except Exception as e:
                logger.error(f"Failed to upload user batch {i + 1}/{total_batches}: {e}")
                self._observability.increment_counter("batch_upload_errors")
                raise

    def _batch_index_groups(self, groups) -> None:
        """Index groups in batches with proper page signaling."""
        if not groups:
            return

        batches = list(BatchProcessor(groups, batch_size=self.batch_size))
        total_batches = len(batches)

        logger.info(f"Uploading {len(groups)} groups in {total_batches} batches")

        upload_id = str(uuid.uuid4())
        for i, batch in enumerate(batches):
            try:
                with api_client() as client:
                    client.indexing.permissions.bulk_index_groups(
                        datasource=self.name,
                        groups=list(batch),
                        upload_id=upload_id,
                        is_first_page=(i == 0),
                        is_last_page=(i == total_batches - 1),
                    )

                logger.info(f"Group batch {i + 1}/{total_batches} uploaded successfully")
                self._observability.increment_counter("batches_uploaded")

            except Exception as e:
                logger.error(f"Failed to upload group batch {i + 1}/{total_batches}: {e}")
                self._observability.increment_counter("batch_upload_errors")
                raise

    def _batch_index_memberships(self, memberships) -> None:
        """Index memberships in batches with proper page signaling."""
        if not memberships:
            return

        batches = list(BatchProcessor(memberships, batch_size=self.batch_size))
        total_batches = len(batches)

        logger.info(f"Uploading {len(memberships)} memberships in {total_batches} batches")

        upload_id = str(uuid.uuid4())
        for i, batch in enumerate(batches):
            try:
                with api_client() as client:
                    client.indexing.permissions.bulk_index_memberships(
                        datasource=self.name,
                        memberships=list(batch),
                        upload_id=upload_id,
                        is_first_page=(i == 0),
                        is_last_page=(i == total_batches - 1),
                    )

                logger.info(f"Membership batch {i + 1}/{total_batches} uploaded successfully")
                self._observability.increment_counter("batches_uploaded")

            except Exception as e:
                logger.error(f"Failed to upload membership batch {i + 1}/{total_batches}: {e}")
                self._observability.increment_counter("batch_upload_errors")
                raise

    def _batch_index_documents(self, documents: Sequence[DocumentDefinition]) -> None:
        """Index documents in batches with proper page signaling."""
        if not documents:
            return

        batches = list(BatchProcessor(list(documents), batch_size=self.batch_size))
        total_batches = len(batches)

        logger.info(f"Uploading {len(documents)} documents in {total_batches} batches")

        upload_id = str(uuid.uuid4())
        for i, batch in enumerate(batches):
            try:
                with api_client() as client:
                    client.indexing.documents.bulk_index(
                        datasource=self.name,
                        documents=list(batch),
                        upload_id=upload_id,
                        is_first_page=(i == 0),
                        is_last_page=(i == total_batches - 1),
                    )

                logger.info(f"Document batch {i + 1}/{total_batches} uploaded successfully")
                self._observability.increment_counter("batches_uploaded")

            except Exception as e:
                logger.error(f"Failed to upload document batch {i + 1}/{total_batches}: {e}")
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
