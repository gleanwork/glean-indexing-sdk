"""Result objects returned by Glean push-layer uploads."""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class BatchUploadResult:
    """Outcome for a single uploaded batch."""

    operation: str
    item_count: int
    batch_index: int
    success: bool = True
    error: Optional[str] = None


@dataclass(frozen=True)
class UploadResult:
    """Summary of an SDK push operation."""

    operation: str
    item_count: int
    batch_count: int
    upload_id: Optional[str] = None
    success: bool = True
    batches: Tuple[BatchUploadResult, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> Tuple[str, ...]:
        """Return error strings captured for failed batches."""
        return tuple(batch.error for batch in self.batches if batch.error)
