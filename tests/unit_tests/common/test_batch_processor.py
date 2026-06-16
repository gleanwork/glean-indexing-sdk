import pytest
from glean.api_client.models import ContentDefinition, DocumentDefinition

from glean.indexing.common import BatchProcessor, DocumentBatchProcessor


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


class TestDocumentBatchProcessor:
    def _document(self, doc_id: str, body: str = "hello") -> DocumentDefinition:
        return DocumentDefinition(
            datasource="test_datasource",
            id=doc_id,
            title=f"Doc {doc_id}",
            view_url=f"https://example.com/{doc_id}",
            body=ContentDefinition(mime_type="text/plain", text_content=body),
        )

    def test_splits_by_serialized_document_bytes(self):
        """Test that documents are batched by serialized byte size."""
        documents = [self._document("1"), self._document("2")]
        processor = DocumentBatchProcessor(
            documents,
            batch_size=10,
            max_batch_bytes=1,
        )

        batches = list(processor)
        assert batches == [[documents[0]], [documents[1]]]

    def test_batch_size_still_applies(self):
        """Test that document count is still respected."""
        documents = [self._document("1"), self._document("2"), self._document("3")]
        processor = DocumentBatchProcessor(
            documents,
            batch_size=2,
            max_batch_bytes=None,
        )

        batches = list(processor)
        assert batches == [[documents[0], documents[1]], [documents[2]]]

    def test_oversized_document_gets_own_batch(self):
        """Test that a single oversized document is still yielded."""
        large_document = self._document("1", body="x" * 100)
        small_document = self._document("2")
        processor = DocumentBatchProcessor(
            [large_document, small_document],
            batch_size=10,
            max_batch_bytes=1,
        )

        batches = list(processor)
        assert batches == [[large_document], [small_document]]

    def test_rejects_invalid_max_batch_bytes(self):
        """Test that invalid byte limits are rejected."""
        with pytest.raises(ValueError, match="max_batch_bytes"):
            DocumentBatchProcessor([self._document("1")], max_batch_bytes=0)
