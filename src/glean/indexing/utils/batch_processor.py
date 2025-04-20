"""Batch processing utility for efficient data handling."""

import logging
from typing import Generic, Iterator, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


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
