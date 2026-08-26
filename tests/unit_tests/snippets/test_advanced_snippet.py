"""Tests for the advanced documentation snippets."""

from importlib import import_module


def test_document_batching_options_are_executable():
    """Keep the documented byte-batching options importable and accurate."""
    snippet = import_module("snippets.advanced.document_batching")

    assert snippet.default_batching.document_batch_size_bytes == 5 * snippet.MIB
    assert snippet.smaller_batches.document_batch_size_bytes == 2 * snippet.MIB
    assert snippet.count_only_batches.document_batch_size_bytes is None
