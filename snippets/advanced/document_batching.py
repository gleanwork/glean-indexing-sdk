from glean.indexing.models import ConnectorOptions

MIB = 1024 * 1024

# The default applies when ConnectorOptions is omitted or used without an override.
default_batching = ConnectorOptions()
assert default_batching.document_batch_size_bytes == 5 * MIB

smaller_batches = ConnectorOptions(document_batch_size_bytes=2 * MIB)
count_only_batches = ConnectorOptions(document_batch_size_bytes=None)
