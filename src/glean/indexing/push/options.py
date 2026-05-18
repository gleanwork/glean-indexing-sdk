"""Options for Glean push-layer uploads."""

from dataclasses import dataclass
from typing import Any, Optional

DEFAULT_DOCUMENT_BATCH_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_UPLOAD_CONCURRENCY = 5


@dataclass
class PushOptions:
    """Controls upload behavior for SDK-owned push operations."""

    force_restart: bool = False
    disable_stale_deletion_check: bool = False
    upload_timeout_ms: Optional[int] = None
    upload_concurrency: int = DEFAULT_UPLOAD_CONCURRENCY
    document_batch_max_bytes: Optional[int] = DEFAULT_DOCUMENT_BATCH_MAX_BYTES
    retries: Optional[Any] = None


def push_options_from_connector_options(options: Optional[Any]) -> PushOptions:
    """Convert connector options into push-layer options.

    The SDK keeps `ConnectorOptions` as the public connector-facing shape while
    allowing the push layer to grow independently.
    """
    if options is None:
        return PushOptions()

    return PushOptions(
        force_restart=getattr(options, "force_restart", False),
        disable_stale_deletion_check=getattr(options, "disable_stale_deletion_check", False),
        upload_timeout_ms=getattr(options, "upload_timeout_ms", None),
        upload_concurrency=getattr(options, "upload_concurrency", DEFAULT_UPLOAD_CONCURRENCY),
        document_batch_max_bytes=getattr(
            options, "document_batch_max_bytes", DEFAULT_DOCUMENT_BATCH_MAX_BYTES
        ),
        retries=getattr(options, "retries", None),
    )
