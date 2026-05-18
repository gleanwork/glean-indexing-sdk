"""Batching primitives for Glean push-layer uploads."""

import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any, TypeVar

T = TypeVar("T")


def iter_batches(items: Sequence[T], *, max_items: int) -> Iterator[list[T]]:
    """Yield count-based batches."""
    if max_items <= 0:
        raise ValueError("max_items must be greater than zero")

    for i in range(0, len(items), max_items):
        yield list(items[i : i + max_items])


def iter_sized_batches(
    items: Iterable[T],
    *,
    max_items: int,
    max_bytes: int | None,
    size_fn: Callable[[T], int],
) -> Iterator[list[T]]:
    """Yield batches bounded by item count and optional serialized byte size."""
    if max_items <= 0:
        raise ValueError("max_items must be greater than zero")

    batch: list[T] = []
    batch_bytes = 0

    for item in items:
        item_bytes = size_fn(item)
        would_exceed_count = len(batch) >= max_items
        would_exceed_bytes = (
            max_bytes is not None and batch and batch_bytes + item_bytes > max_bytes
        )

        if would_exceed_count or would_exceed_bytes:
            yield batch
            batch = []
            batch_bytes = 0

        batch.append(item)
        batch_bytes += item_bytes

    if batch:
        yield batch


def json_size_bytes(value: Any) -> int:
    """Best-effort JSON byte size for generated client model objects."""
    if hasattr(value, "model_dump"):
        serializable = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    elif isinstance(value, dict):
        serializable = value
    else:
        serializable = repr(value)

    return len(json.dumps(serializable, separators=(",", ":"), default=str).encode("utf-8"))
