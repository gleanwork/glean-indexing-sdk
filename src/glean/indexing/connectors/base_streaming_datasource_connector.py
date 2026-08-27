"""Base streaming datasource connector for memory-efficient processing of large datasets."""

import logging
import time
import uuid
from abc import ABC
from typing import Generator, Optional, Sequence

from glean.api_client.models import DocumentDefinition
from glean.indexing.common import DocumentBatchProcessor
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode, TSourceData

logger = logging.getLogger(__name__)


class BaseStreamingDatasourceConnector(BaseDatasourceConnector[TSourceData], ABC):
    """
    Base class for all Glean streaming datasource connectors.

    This class provides the core logic for memory-efficient indexing of large document/content datasets from external systems into Glean.
    It fetches source data incrementally from a generator and uploads documents in bulk batches, so it can be used for full crawls
    without loading the entire dataset into memory.
    Subclasses must define a `configuration` attribute of type `CustomDatasourceConfig` describing the datasource.

    To implement a custom streaming connector, inherit from this class and implement:
        - configuration: CustomDatasourceConfig (class or instance attribute)
        - get_data(self, since: Optional[str] = None) -> Generator[TSourceData, None, None]
        - transform(self, data: Sequence[TSourceData]) -> Sequence[DocumentDefinition]

    Attributes:
        name (str): The unique name of the connector (should be snake_case).
        configuration (CustomDatasourceConfig): The datasource configuration for Glean registration.
        batch_size (int): The batch size for uploads (default: 1000).
        data_client (BaseStreamingDataClient): The streaming data client for fetching source data.
        observability (ConnectorObservability): Observability and metrics for this connector.

    Notes:
        - Use this class for very large datasets, paginated APIs, or memory-constrained environments.
        - The data client should yield data incrementally (e.g., via a generator).

    Example:
        class MyStreamingConnector(BaseStreamingDatasourceConnector[MyDocData]):
            configuration = CustomDatasourceConfig(...)
            ...
    """

    def __init__(self, name: str, data_client: BaseStreamingDataClient[TSourceData]):
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
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """
        Index data from the datasource to Glean using streaming.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            options: Optional connector options for controlling indexing behavior.
        """
        self._observability.start_execution()
        items_fetched = 0
        documents_transformed = 0
        data_fetch_duration = 0.0
        data_transform_duration = 0.0

        try:
            logger.info(
                f"Starting {mode.name.lower()} streaming indexing for datasource '{self.name}'"
            )

            since = None
            if mode == IndexingMode.INCREMENTAL:
                since = self._get_last_crawl_timestamp()
                logger.info(f"Incremental crawl since: {since}")

            upload_id = self.generate_upload_id()
            self._force_restart = options.force_restart if options else False
            batch_count = 0
            max_batch_bytes = self._resolve_max_batch_bytes(options)

            def transformed_batches() -> Generator[Sequence[DocumentDefinition], None, None]:
                nonlocal batch_count
                nonlocal data_fetch_duration
                nonlocal data_transform_duration
                nonlocal documents_transformed
                nonlocal items_fetched

                data_iterator = iter(self.get_data(since=since))
                while True:
                    batch: list[TSourceData] = []
                    while len(batch) < self.batch_size:
                        fetch_started = time.perf_counter()
                        try:
                            item = next(data_iterator)
                        except StopIteration:
                            break
                        finally:
                            data_fetch_duration += time.perf_counter() - fetch_started
                        batch.append(item)
                        items_fetched += 1

                    if not batch:
                        break

                    logger.info(f"Processing batch {batch_count} with {len(batch)} items")
                    transform_started = time.perf_counter()
                    try:
                        transformed_batch = self.transform(batch)
                    finally:
                        data_transform_duration += time.perf_counter() - transform_started
                    documents_transformed += len(transformed_batch)
                    logger.info(
                        f"Transformed batch {batch_count}: {len(transformed_batch)} documents"
                    )
                    batch_count += 1
                    yield from DocumentBatchProcessor(
                        transformed_batch,
                        batch_size=self.batch_size,
                        max_batch_bytes=max_batch_bytes,
                    )

            uploader = self._create_uploader(options)
            if mode == IndexingMode.INCREMENTAL:
                for document_batch in transformed_batches():
                    uploader.index_documents(document_batch, upload_id=upload_id)
            else:
                if self._force_restart:
                    logger.info("Force restarting upload - discarding any previous upload progress")

                uploader.bulk_index_document_batches(
                    transformed_batches(),
                    upload_id=upload_id,
                    force_restart_upload=True if self._force_restart else None,
                    disable_stale_document_deletion_check=True
                    if (options and options.disable_stale_deletion_check)
                    else None,
                )

            self._observability.record_metric("documents_indexed", documents_transformed)
            logger.info(
                f"Streaming indexing completed successfully. Processed {batch_count} batches."
            )

        except Exception as e:
            logger.exception(f"Error during streaming indexing: {e}")
            self._observability.increment_counter("indexing_errors")
            raise
        finally:
            self._observability.record_metric("items_fetched", items_fetched)
            self._observability.record_metric("documents_transformed", documents_transformed)
            self._observability.record_metric("data_fetch_duration", data_fetch_duration)
            self._observability.record_metric("data_transform_duration", data_transform_duration)
            self._observability.end_execution()

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
