from glean.indexing.common import BatchProcessor, SizedBatchProcessor


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


class TestSizedBatchProcessor:
    def test_splits_by_max_batch_bytes(self):
        """Test that data is batched by byte size."""
        processor = SizedBatchProcessor(
            ["aa", "bb", "cc"],
            batch_size=10,
            max_batch_bytes=4,
            size_func=len,
        )

        batches = list(processor)
        assert batches == [["aa", "bb"], ["cc"]]

    def test_batch_size_still_applies(self):
        """Test that item count is still respected."""
        processor = SizedBatchProcessor(
            ["a", "b", "c"],
            batch_size=2,
            max_batch_bytes=10,
            size_func=len,
        )

        batches = list(processor)
        assert batches == [["a", "b"], ["c"]]

    def test_oversized_item_gets_own_batch(self):
        """Test that a single oversized item is still yielded."""
        processor = SizedBatchProcessor(
            ["abcdef", "g"],
            batch_size=10,
            max_batch_bytes=3,
            size_func=len,
        )

        batches = list(processor)
        assert batches == [["abcdef"], ["g"]]

    def test_max_batch_bytes_requires_size_func(self):
        """Test that byte batching requires a size function."""
        try:
            SizedBatchProcessor(["a"], max_batch_bytes=3)
        except ValueError as e:
            assert "size_func" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    def test_batch_size_equal_to_data(self):
        """Test when batch size is equal to the data size."""
        data = list(range(5))
        processor = BatchProcessor(data, batch_size=5)

        batches = list(processor)
        assert len(batches) == 1
        assert batches[0] == [0, 1, 2, 3, 4]
