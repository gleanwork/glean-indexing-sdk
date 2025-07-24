"""Base streaming datasource connector for memory-efficient processing of large datasets."""

import logging
import uuid
from abc import ABC
from typing import Generator, List, Optional, Sequence

from glean.indexing.common import api_client
from glean.indexing.connectors import BaseDatasourceConnector, StreamingConnectorDataClient
from glean.indexing.models import IndexingMode, TSourceData

logger = logging.getLogger(__name__)


class BaseStreamingDatasourceConnector(BaseDatasourceConnector[TSourceData], ABC):
    """
    Base class for all Glean streaming datasource connectors.

    This class provides the core logic for memory-efficient, incremental indexing of large document/content datasets from external systems into Glean.
    Subclasses must define a `configuration` attribute of type `CustomDatasourceConfig` describing the datasource.

    To implement a custom streaming connector, inherit from this class and implement:
        - configuration: CustomDatasourceConfig (class or instance attribute)
        - get_data(self, since: Optional[str] = None) -> Generator[TSourceData, None, None]
        - transform(self, data: Sequence[TSourceData]) -> Sequence[DocumentDefinition]

    Attributes:
        name (str): The unique name of the connector (should be snake_case).
        configuration (CustomDatasourceConfig): The datasource configuration for Glean registration.
        batch_size (int): The batch size for uploads (default: 1000).
        data_client (StreamingConnectorDataClient): The streaming data client for fetching source data.
        observability (ConnectorObservability): Observability and metrics for this connector.

    Notes:
        - Use this class for very large datasets, paginated APIs, or memory-constrained environments.
        - The data client should yield data incrementally (e.g., via a generator).

    Example:
        class MyStreamingConnector(BaseStreamingDatasourceConnector[MyDocData]):
            configuration = CustomDatasourceConfig(...)
            ...
    """

    def __init__(self, name: str, data_client: StreamingConnectorDataClient[TSourceData]):
        # Note: We pass the streaming client as-is since it's a specialized version
        # The type checker may warn about this, but it's intentional for streaming
        super().__init__(name, data_client)  # type: ignore[arg-type]
        self.batch_size = 1000
        self._upload_id: Optional[str] = None
        self._force_restart: bool = False

    def generate_upload_id(self) -> str:
        """Generate a unique upload ID for batch tracking."""
        if not self._upload_id:
            self._upload_id = str(uuid.uuid4())
        return self._upload_id

    def get_data(self, since: Optional[str] = None) -> Generator[TSourceData, None, None]:
        """
        Get data from the streaming data client.

        Args:
            since: If provided, only get data modified since this timestamp.

        Yields:
            Individual data items from the source
        """
        logger.info(f"Fetching streaming data from source{' since ' + since if since else ''}")
        yield from self.data_client.get_source_data(since=since)

    def index_data(
        self, mode: IndexingMode = IndexingMode.FULL, force_restart: bool = False
    ) -> None:
        """
        Index data from the datasource to Glean using streaming.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            force_restart: If True, forces a restart of the upload, discarding any previous upload progress.
                          This sets forceRestartUpload=True on the first batch and generates a new upload ID.
        """
        logger.info(f"Starting {mode.name.lower()} streaming indexing for datasource '{self.name}'")

        since = None
        if mode == IndexingMode.INCREMENTAL:
            since = "2023-01-01T00:00:00Z"

        upload_id = self.generate_upload_id()
        self._force_restart = force_restart
        data_iterator = self.get_data(since=since)
        is_first_batch = True
        batch: List[TSourceData] = []
        batch_count = 0

        try:
            for item in data_iterator:
                batch.append(item)

                if len(batch) == self.batch_size:
                    try:
                        next_item = next(data_iterator)

                        self._process_batch(
                            batch=batch,
                            upload_id=upload_id,
                            is_first_batch=is_first_batch,
                            is_last_batch=False,
                            batch_number=batch_count,
                        )

                        batch_count += 1
                        batch = [next_item]
                        is_first_batch = False

                    except StopIteration:
                        break

            if batch:
                self._process_batch(
                    batch=batch,
                    upload_id=upload_id,
                    is_first_batch=is_first_batch,
                    is_last_batch=True,
                    batch_number=batch_count,
                )

            logger.info(
                f"Streaming indexing completed successfully. Processed {batch_count + 1} batches."
            )

        except Exception as e:
            logger.exception(f"Error during streaming indexing: {e}")
            raise

    def _process_batch(
        self,
        batch: List[TSourceData],
        upload_id: str,
        is_first_batch: bool,
        is_last_batch: bool,
        batch_number: int,
    ) -> None:
        """
        Process a single batch of data.

        Args:
            batch: The batch of raw data to process
            upload_id: The upload ID for this indexing session
            is_first_batch: Whether this is the first batch
            is_last_batch: Whether this is the last batch
            batch_number: The sequence number of this batch
        """
        logger.info(f"Processing batch {batch_number} with {len(batch)} items")

        try:
            transformed_batch = self.transform(batch)
            logger.info(f"Transformed batch {batch_number}: {len(transformed_batch)} documents")

            bulk_index_kwargs = {
                "datasource": self.name,
                "documents": list(transformed_batch),
                "upload_id": upload_id,
                "is_first_page": is_first_batch,
                "is_last_page": is_last_batch,
            }

            if self._force_restart and is_first_batch:
                bulk_index_kwargs["forceRestartUpload"] = True
                logger.info("Force restarting upload - discarding any previous upload progress")

            with api_client() as client:
                client.indexing.documents.bulk_index(**bulk_index_kwargs)

            logger.info(f"Batch {batch_number} indexed successfully")

        except Exception as e:
            logger.error(f"Failed to process batch {batch_number}: {e}")
            raise

    def get_data_non_streaming(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """
        Get all data at once (non-streaming mode).

        This method is required by the base class but shouldn't be used
        for streaming connectors as it defeats the purpose of streaming.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of source data items from the external system.
        """
        logger.warning(
            "get_data_non_streaming called on streaming connector - this may cause memory issues"
        )
        return list(self.get_data(since=since))
