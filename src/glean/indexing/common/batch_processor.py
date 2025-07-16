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
            
        Raises:
            ValueError: If batch_size is not a positive integer or exceeds maximum allowed size.
        """
        if not isinstance(batch_size, int):
            raise ValueError(f"batch_size must be an integer, got {type(batch_size).__name__}")
        
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
            
        # Prevent excessively large batch sizes that could cause memory issues
        max_batch_size = 10000
        if batch_size > max_batch_size:
            logger.warning(f"batch_size {batch_size} exceeds recommended maximum {max_batch_size}, "
                          f"using {max_batch_size} instead")
            batch_size = max_batch_size
        
        self.data = data
        self.batch_size = batch_size

    def __iter__(self) -> Iterator[Sequence[T]]:
        """Iterate over the data in batches.

        Yields:
            Sequences of items of size batch_size (except possibly the last batch).
        """
        for i in range(0, len(self.data), self.batch_size):
            yield self.data[i : i + self.batch_size]
