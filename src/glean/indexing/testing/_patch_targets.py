"""Registry of `api_client` import sites that the test mock helpers must patch.

When a connector base class calls `with api_client() as client:`, the `api_client`
symbol it resolves is the one bound at import time in that module. To intercept
those calls, `unittest.mock.patch` must target each connector module's local
`api_client` reference. Adding a new connector base class without registering
its module here means the test helpers will silently fail to mock it.
"""

import importlib
from typing import Tuple

_PATCH_TARGETS: Tuple[str, ...] = (
    "glean.indexing.connectors.base_datasource_connector.api_client",
    "glean.indexing.connectors.base_streaming_datasource_connector.api_client",
    "glean.indexing.connectors.base_async_streaming_datasource_connector.api_client",
    "glean.indexing.connectors.base_people_connector.api_client",
)

_validated: bool = False


def validate_patch_targets() -> None:
    """Verify every entry in `_PATCH_TARGETS` is a real module attribute.

    Lazy and idempotent: runs once on the first call (typically the first
    `mock_glean_client()` enter), then short-circuits. Raises `RuntimeError`
    listing any missing modules or attributes so failures are loud and
    self-explanatory.
    """
    global _validated
    if _validated:
        return

    missing: list[str] = []
    for target in _PATCH_TARGETS:
        module_path, _, attr = target.rpartition(".")
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            missing.append(f"{target} (import failed: {exc})")
            continue
        if not hasattr(module, attr):
            missing.append(f"{target} ({attr!r} not found in {module_path})")

    if missing:
        raise RuntimeError(
            "glean.indexing.testing patch targets are out of sync with the codebase. "
            "Missing or renamed:\n  - " + "\n  - ".join(missing) + "\n"
            "Update _PATCH_TARGETS in glean/indexing/testing/_patch_targets.py."
        )

    _validated = True
