"""Batch processing utility for efficient data handling."""

import json
import logging
from typing import Callable, Generic, Iterator, Optional, Sequence, TypeVar

from glean.api_client.models import DocumentDefinition

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_DOCUMENT_BATCH_SIZE_BYTES = 5 * 1024 * 1024


class BatchProcessor(Generic[T]):
    """A utility for processing data in batches."""

    def __init__(self, data: Sequence[T], batch_size: int = 100):
        """Initialize the BatchProcessor.

        Args:
            data: The data to process in batches.
            batch_size: The size of each batch.
        """
        self.data = data
        self.batch_size = batch_size

    def __iter__(self) -> Iterator[Sequence[T]]:
        """Iterate over the data in batches.

        Yields:
            Sequences of items of size batch_size (except possibly the last batch).
        """
        for i in range(0, len(self.data), self.batch_size):
            yield self.data[i : i + self.batch_size]


class _SizedBatchProcessor(Generic[T]):
    """A utility for processing data in batches constrained by item count and bytes."""

    def __init__(
        self,
        data: Sequence[T],
        *,
        batch_size: int = 100,
        max_batch_bytes: Optional[int] = None,
        size_func: Optional[Callable[[T], int]] = None,
    ):
        """Initialize the _SizedBatchProcessor.

        Args:
            data: The data to process in batches.
            batch_size: The maximum number of items in each batch.
            max_batch_bytes: Optional maximum byte size for each batch.
            size_func: Function used to measure each item's byte size when
                max_batch_bytes is set.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if max_batch_bytes is not None and max_batch_bytes <= 0:
            raise ValueError("max_batch_bytes must be greater than 0")
        if max_batch_bytes is not None and size_func is None:
            raise ValueError("size_func is required when max_batch_bytes is set")

        self.data = data
        self.batch_size = batch_size
        self.max_batch_bytes = max_batch_bytes
        self.size_func = size_func

    def __iter__(self) -> Iterator[Sequence[T]]:
        """Iterate over data in count- and byte-constrained batches."""
        batch: list[T] = []
        batch_bytes = 0

        for item in self.data:
            item_bytes = self.size_func(item) if self.size_func else 0

            if batch and (
                len(batch) >= self.batch_size
                or (
                    self.max_batch_bytes is not None
                    and batch_bytes + item_bytes > self.max_batch_bytes
                )
            ):
                yield batch
                batch = []
                batch_bytes = 0

            batch.append(item)
            batch_bytes += item_bytes

        if batch:
            yield batch


class DocumentBatchProcessor(_SizedBatchProcessor[DocumentDefinition]):
    """Batch processor for documents using serialized document size."""

    def __init__(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        batch_size: int = 100,
        max_batch_bytes: Optional[int] = DEFAULT_DOCUMENT_BATCH_SIZE_BYTES,
    ):
        """Initialize a document batch processor.

        Args:
            documents: Documents to process in batches.
            batch_size: The maximum number of documents in each batch.
            max_batch_bytes: Optional maximum serialized byte size for each batch.
        """
        super().__init__(
            documents,
            batch_size=batch_size,
            max_batch_bytes=max_batch_bytes,
            size_func=_document_size_bytes if max_batch_bytes is not None else None,
        )


def _document_size_bytes(document: DocumentDefinition) -> int:
    """Return the UTF-8 byte size of a serialized document."""
    return len(
        json.dumps(
            document.model_dump(by_alias=True, exclude_none=True),
            separators=(",", ":"),
        ).encode("utf-8")
    )
