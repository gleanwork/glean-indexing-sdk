"""Base datasource connector for the Glean Connector SDK."""

import logging
from abc import ABC
from typing import Optional, Sequence

from glean.api_client.models import DocumentDefinition
from glean.indexing.common import api_client
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
from glean.indexing.push.options import push_options_from_connector_options
from glean.indexing.push.uploader import PushUploader

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

        with api_client() as client:
            # Use attribute access instead of model_dump() because certain
            # pydantic/api-client version combinations return camelCase aliases
            # even with by_alias=False, and datasources.add() expects snake_case.
            kwargs = {
                name: getattr(config, name)
                for name in type(config).model_fields
                if name in config.model_fields_set
            }
            client.indexing.datasources.add(**kwargs)
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
                self._batch_index_users(users, options=options)

            groups = identities.get("groups")
            if groups:
                logger.info(f"Indexing {len(groups)} groups")
                self._batch_index_groups(groups, options=options)

                memberships = identities.get("memberships")
                if not memberships:
                    raise InconsistentDataError(
                        "identity data",
                        "Groups were provided, but no memberships were provided",
                        "Implement get_identities() to return both 'groups' and 'memberships' keys, "
                        "or remove groups if memberships are not available",
                    )

                logger.info(f"Indexing {len(memberships)} memberships")
                self._batch_index_memberships(memberships, options=options)

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
                self._batch_index_documents(documents, options=options)
            self._observability.end_timer("data_upload")

            logger.info(f"Successfully indexed {len(documents)} documents to Glean")
            self._observability.record_metric("documents_indexed", len(documents))

        except Exception as e:
            logger.exception(f"Error during indexing: {e}")
            self._observability.increment_counter("indexing_errors")
            raise
        finally:
            self._observability.end_execution()

    def _batch_index_users(self, users, options: Optional[ConnectorOptions] = None) -> None:
        """Index users in batches with proper page signaling."""
        if not users:
            return

        try:
            result = PushUploader(api_client).upload_users(
                datasource=self.name,
                users=users,
                batch_size=self.batch_size,
                options=push_options_from_connector_options(options),
            )
            self._observability.increment_counter("batches_uploaded", result.batch_count)
        except Exception as e:
            logger.error(f"Failed to upload users: {e}")
            self._observability.increment_counter("batch_upload_errors")
            raise

    def _batch_index_groups(self, groups, options: Optional[ConnectorOptions] = None) -> None:
        """Index groups in batches with proper page signaling."""
        if not groups:
            return

        try:
            result = PushUploader(api_client).upload_groups(
                datasource=self.name,
                groups=groups,
                batch_size=self.batch_size,
                options=push_options_from_connector_options(options),
            )
            self._observability.increment_counter("batches_uploaded", result.batch_count)
        except Exception as e:
            logger.error(f"Failed to upload groups: {e}")
            self._observability.increment_counter("batch_upload_errors")
            raise

    def _batch_index_memberships(
        self, memberships, options: Optional[ConnectorOptions] = None
    ) -> None:
        """Index memberships in batches with proper page signaling."""
        if not memberships:
            return

        try:
            result = PushUploader(api_client).upload_memberships(
                datasource=self.name,
                memberships=memberships,
                batch_size=self.batch_size,
                options=push_options_from_connector_options(options),
            )
            self._observability.increment_counter("batches_uploaded", result.batch_count)
        except Exception as e:
            logger.error(f"Failed to upload memberships: {e}")
            self._observability.increment_counter("batch_upload_errors")
            raise

    def _batch_index_documents(
        self,
        documents: Sequence[DocumentDefinition],
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Index documents in batches with proper page signaling.

        Args:
            documents: The documents to index
            options: Optional connector options for controlling indexing behavior
        """
        if not documents:
            return

        try:
            push_options = push_options_from_connector_options(options)
            result = PushUploader(api_client).upload_documents(
                datasource=self.name,
                documents=documents,
                batch_size=self.batch_size,
                options=push_options,
            )
            self._observability.increment_counter("batches_uploaded", result.batch_count)
        except Exception as e:
            logger.error(f"Failed to upload documents: {e}")
            self._observability.increment_counter("batch_upload_errors")
            raise

    def index_documents(
        self,
        documents: Sequence[DocumentDefinition],
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Incrementally upsert one or more documents through `indexdocuments`."""
        PushUploader(api_client).index_documents(
            datasource=self.name,
            documents=documents,
            batch_size=self.batch_size,
            options=push_options_from_connector_options(options),
        )

    def index_users(self, users, options: Optional[ConnectorOptions] = None) -> None:
        """Incrementally index datasource users through `indexuser`."""
        PushUploader(api_client).index_users(
            datasource=self.name,
            users=users,
            options=push_options_from_connector_options(options),
        )

    def index_groups(self, groups, options: Optional[ConnectorOptions] = None) -> None:
        """Incrementally index datasource groups through `indexgroup`."""
        PushUploader(api_client).index_groups(
            datasource=self.name,
            groups=groups,
            options=push_options_from_connector_options(options),
        )

    def index_memberships(self, memberships, options: Optional[ConnectorOptions] = None) -> None:
        """Incrementally index datasource memberships through `indexmembership`."""
        PushUploader(api_client).index_memberships(
            datasource=self.name,
            memberships=memberships,
            options=push_options_from_connector_options(options),
        )

    def delete_document(
        self,
        *,
        object_type: str,
        id: str,
        options: Optional[ConnectorOptions] = None,
        version: Optional[int] = None,
    ) -> None:
        """Delete a document from this datasource."""
        PushUploader(api_client).delete_document(
            datasource=self.name,
            object_type=object_type,
            id=id,
            version=version,
            options=push_options_from_connector_options(options),
        )

    def delete_user(
        self,
        *,
        email: str,
        options: Optional[ConnectorOptions] = None,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource user by email."""
        PushUploader(api_client).delete_user(
            datasource=self.name,
            email=email,
            version=version,
            options=push_options_from_connector_options(options),
        )

    def delete_group(
        self,
        *,
        group_name: str,
        options: Optional[ConnectorOptions] = None,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource group by name."""
        PushUploader(api_client).delete_group(
            datasource=self.name,
            group_name=group_name,
            version=version,
            options=push_options_from_connector_options(options),
        )

    def delete_membership(
        self,
        *,
        membership,
        options: Optional[ConnectorOptions] = None,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource membership."""
        PushUploader(api_client).delete_membership(
            datasource=self.name,
            membership=membership,
            version=version,
            options=push_options_from_connector_options(options),
        )

    def update_permissions(
        self,
        *,
        permissions,
        object_type: Optional[str] = None,
        id: Optional[str] = None,
        view_url: Optional[str] = None,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Update document permissions by document ID or view URL."""
        PushUploader(api_client).update_permissions(
            datasource=self.name,
            permissions=permissions,
            object_type=object_type,
            id=id,
            view_url=view_url,
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
