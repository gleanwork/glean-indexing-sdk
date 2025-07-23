from glean.indexing.common import BatchProcessor


class TestBatchProcessor:
    def test_batch_processing(self):
        """Test that data is properly batched."""
        data = list(range(10))
        processor = BatchProcessor(data, batch_size=3)

        batches = list(processor)
        assert len(batches) == 4
        assert batches[0] == [0, 1, 2]
        assert batches[1] == [3, 4, 5]
        assert batches[2] == [6, 7, 8]
        assert batches[3] == [9]

    def test_empty_data(self):
        """Test that empty data produces no batches."""
        processor = BatchProcessor([], batch_size=5)
        batches = list(processor)
        assert len(batches) == 0

    def test_batch_size_larger_than_data(self):
        """Test when batch size is larger than the data."""
        data = list(range(5))
        processor = BatchProcessor(data, batch_size=10)

        batches = list(processor)
        assert len(batches) == 1
        assert batches[0] == [0, 1, 2, 3, 4]

    def test_batch_size_equal_to_data(self):
        """Test when batch size is equal to the data size."""
        data = list(range(5))
        processor = BatchProcessor(data, batch_size=5)

        batches = list(processor)
        assert len(batches) == 1
        assert batches[0] == [0, 1, 2, 3, 4]
