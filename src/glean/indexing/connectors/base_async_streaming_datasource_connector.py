"""Base async streaming datasource connector for memory-efficient processing of large datasets."""

import asyncio
import logging
import uuid
from abc import ABC
from typing import AsyncGenerator, List, Optional, Sequence

from glean.api_client.models import DocumentDefinition
from glean.indexing.common import DocumentBatchProcessor
from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.models import (
    DEFAULT_UPLOAD_MAX_WORKERS,
    ConnectorOptions,
    IndexingMode,
    TSourceData,
)

logger = logging.getLogger(__name__)


class BaseAsyncStreamingDatasourceConnector(BaseDatasourceConnector[TSourceData], ABC):
    """
    Base class for async streaming datasource connectors.

    This class provides async-native streaming for memory-efficient processing
    of large datasets. Use this when your data source provides async APIs
    (e.g., aiohttp, httpx async, etc.).

    To implement a custom async streaming connector, inherit from this class and implement:
        - configuration: CustomDatasourceConfig (class or instance attribute)
        - async_data_client: BaseAsyncStreamingDataClient (set in __init__)
        - transform(self, data: Sequence[TSourceData]) -> Sequence[DocumentDefinition]

    Attributes:
        name (str): The unique name of the connector (should be snake_case).
        configuration (CustomDatasourceConfig): The datasource configuration.
        batch_size (int): The batch size for uploads (default: 1000).
        async_data_client (BaseAsyncStreamingDataClient): The async streaming data client.

    Example:
        class MyAsyncConnector(BaseAsyncStreamingDatasourceConnector[MyDocData]):
            configuration = CustomDatasourceConfig(...)

            def __init__(self, name: str):
                async_client = MyAsyncDataClient()
                super().__init__(name, async_client)

            def transform(self, data: Sequence[MyDocData]) -> Sequence[DocumentDefinition]:
                return [self._transform_doc(d) for d in data]
    """

    def __init__(
        self,
        name: str,
        async_data_client: BaseAsyncStreamingDataClient[TSourceData],
    ):
        super().__init__(name, None)  # type: ignore[arg-type]
        self.async_data_client = async_data_client
        self.batch_size = 1000
        self._upload_id: Optional[str] = None
        self._force_restart: bool = False

    def generate_upload_id(self) -> str:
        """Generate a unique upload ID for batch tracking."""
        if not self._upload_id:
            self._upload_id = str(uuid.uuid4())
        return self._upload_id

    async def get_data_async(
        self, since: Optional[str] = None
    ) -> AsyncGenerator[TSourceData, None]:
        """
        Get data from the async streaming data client.

        Args:
            since: If provided, only get data modified since this timestamp.

        Yields:
            Individual data items from the source
        """
        logger.info(
            f"Fetching async streaming data from source{' since ' + since if since else ''}"
        )
        async for item in self.async_data_client.get_source_data(since=since):
            yield item

    async def index_data_async(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """
        Index data from the datasource to Glean using async streaming.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            options: Optional connector options for controlling indexing behavior.
        """
        logger.info(
            f"Starting {mode.name.lower()} async streaming indexing for datasource '{self.name}'"
        )

        since = None
        if mode == IndexingMode.INCREMENTAL:
            since = self._get_last_crawl_timestamp()
            logger.info(f"Incremental crawl since: {since}")

        upload_id = self.generate_upload_id()
        self._force_restart = options.force_restart if options else False
        batch_count = 0
        max_batch_bytes = self._resolve_max_batch_bytes(options)
        upload_max_workers = options.upload_max_workers if options else DEFAULT_UPLOAD_MAX_WORKERS
        uploader = self._create_uploader(options)

        try:

            async def transformed_batches() -> AsyncGenerator[Sequence[DocumentDefinition], None]:
                nonlocal batch_count
                batch: List[TSourceData] = []
                async for item in self.get_data_async(since=since):
                    batch.append(item)
                    if len(batch) < self.batch_size:
                        continue
                    logger.info(f"Processing batch {batch_count} with {len(batch)} items")
                    transformed_batch = self.transform(batch)
                    logger.info(
                        f"Transformed batch {batch_count}: {len(transformed_batch)} documents"
                    )
                    batch_count += 1
                    for sub_batch in DocumentBatchProcessor(
                        transformed_batch,
                        batch_size=self.batch_size,
                        max_batch_bytes=max_batch_bytes,
                    ):
                        yield sub_batch
                    batch = []
                if batch:
                    logger.info(f"Processing batch {batch_count} with {len(batch)} items")
                    transformed_batch = self.transform(batch)
                    logger.info(
                        f"Transformed batch {batch_count}: {len(transformed_batch)} documents"
                    )
                    batch_count += 1
                    for sub_batch in DocumentBatchProcessor(
                        transformed_batch,
                        batch_size=self.batch_size,
                        max_batch_bytes=max_batch_bytes,
                    ):
                        yield sub_batch

            batch_iterator = transformed_batches().__aiter__()
            try:
                first_batch = await batch_iterator.__anext__()
            except StopAsyncIteration:
                first_batch = None

            if first_batch is not None:
                try:
                    second_batch = await batch_iterator.__anext__()
                except StopAsyncIteration:
                    second_batch = None

                if second_batch is None:
                    await asyncio.to_thread(
                        uploader.bulk_index_single_batch_upload,
                        documents=list(first_batch),
                        upload_id=upload_id,
                        is_first_page=True,
                        is_last_page=True,
                        force_restart_upload=True if self._force_restart else None,
                        disable_stale_document_deletion_check=True
                        if (options and options.disable_stale_deletion_check)
                        else None,
                    )
                else:
                    await asyncio.to_thread(
                        uploader.bulk_index_single_batch_upload,
                        documents=list(first_batch),
                        upload_id=upload_id,
                        is_first_page=True,
                        is_last_page=False,
                        force_restart_upload=True if self._force_restart else None,
                        disable_stale_document_deletion_check=None,
                    )

                    pending: set[asyncio.Task[None]] = set()
                    current_batch = second_batch
                    current_index = 1
                    try:
                        while True:
                            try:
                                next_batch = await batch_iterator.__anext__()
                            except StopAsyncIteration:
                                break
                            pending.add(
                                asyncio.create_task(
                                    asyncio.to_thread(
                                        uploader.bulk_index_single_batch_upload,
                                        documents=list(current_batch),
                                        upload_id=upload_id,
                                        is_first_page=False,
                                        is_last_page=False,
                                        batch_index=current_index,
                                        force_restart_upload=None,
                                        disable_stale_document_deletion_check=None,
                                    )
                                )
                            )
                            if len(pending) >= upload_max_workers:
                                done, pending = await asyncio.wait(
                                    pending, return_when=asyncio.FIRST_COMPLETED
                                )
                                errors = [
                                    error
                                    for task in done
                                    if (error := task.exception()) is not None
                                ]
                                if errors:
                                    raise errors[0]
                            current_batch = next_batch
                            current_index += 1

                        if pending:
                            await asyncio.gather(*pending)
                    except BaseException:
                        await asyncio.gather(*pending, return_exceptions=True)
                        raise

                    await asyncio.to_thread(
                        uploader.bulk_index_single_batch_upload,
                        documents=list(current_batch),
                        upload_id=upload_id,
                        is_first_page=False,
                        is_last_page=True,
                        batch_index=current_index,
                        force_restart_upload=None,
                        disable_stale_document_deletion_check=True
                        if (options and options.disable_stale_deletion_check)
                        else None,
                    )

            logger.info(
                f"Async streaming indexing completed successfully. Processed {batch_count} batches."
            )

        except Exception as e:
            logger.exception(f"Error during async streaming indexing: {e}")
            raise

    def get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """
        Sync fallback - collects all data into memory.

        Warning: This defeats the purpose of streaming. Use get_data_async() instead.
        """

        async def collect() -> List[TSourceData]:
            result: List[TSourceData] = []
            async for item in self.get_data_async(since=since):
                result.append(item)
            return result

        logger.warning(
            "Sync get_data() called on async connector - using asyncio.run(). "
            "Consider using get_data_async() for better performance."
        )
        return asyncio.run(collect())

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """
        Sync fallback for index_data.

        Warning: This blocks the current thread. Use index_data_async() instead.
        """
        logger.warning(
            "Sync index_data() called on async connector - using asyncio.run(). "
            "Consider using index_data_async() for better performance."
        )
        asyncio.run(self.index_data_async(mode=mode, options=options))
