"""Base async streaming datasource connector for memory-efficient processing of large datasets."""

import asyncio
import logging
import uuid
from abc import ABC
from typing import AsyncGenerator, List, Optional, Sequence

from glean.indexing.common import api_client
from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.models import IndexingMode, TSourceData

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
        self, mode: IndexingMode = IndexingMode.FULL, force_restart: bool = False
    ) -> None:
        """
        Index data from the datasource to Glean using async streaming.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
            force_restart: If True, forces a restart of the upload.
        """
        logger.info(
            f"Starting {mode.name.lower()} async streaming indexing for datasource '{self.name}'"
        )

        since = None
        if mode == IndexingMode.INCREMENTAL:
            since = self._get_last_crawl_timestamp()
            logger.info(f"Incremental crawl since: {since}")

        upload_id = self.generate_upload_id()
        self._force_restart = force_restart
        is_first_batch = True
        batch: List[TSourceData] = []
        batch_count = 0

        try:
            data_iterator = self.get_data_async(since=since).__aiter__()
            exhausted = False

            while not exhausted:
                try:
                    item = await data_iterator.__anext__()
                    batch.append(item)

                    if len(batch) == self.batch_size:
                        try:
                            next_item = await data_iterator.__anext__()

                            await self._process_batch_async(
                                batch=batch,
                                upload_id=upload_id,
                                is_first_batch=is_first_batch,
                                is_last_batch=False,
                                batch_number=batch_count,
                            )

                            batch_count += 1
                            batch = [next_item]
                            is_first_batch = False

                        except StopAsyncIteration:
                            exhausted = True

                except StopAsyncIteration:
                    exhausted = True

            if batch:
                await self._process_batch_async(
                    batch=batch,
                    upload_id=upload_id,
                    is_first_batch=is_first_batch,
                    is_last_batch=True,
                    batch_number=batch_count,
                )
                batch_count += 1

            logger.info(
                f"Async streaming indexing completed successfully. Processed {batch_count} batches."
            )

        except Exception as e:
            logger.exception(f"Error during async streaming indexing: {e}")
            raise

    async def _process_batch_async(
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
        self, mode: IndexingMode = IndexingMode.FULL, force_restart: bool = False
    ) -> None:
        """
        Sync fallback for index_data.

        Warning: This blocks the current thread. Use index_data_async() instead.
        """
        logger.warning(
            "Sync index_data() called on async connector - using asyncio.run(). "
            "Consider using index_data_async() for better performance."
        )
        asyncio.run(self.index_data_async(mode=mode, force_restart=force_restart))
