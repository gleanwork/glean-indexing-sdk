"""Versioned fixture metadata for the test harness cache.

Each recorded fixture directory contains a ``manifest.json`` alongside the
``data.ndjson`` file.  The manifest lets the harness detect staleness when the
SDK version changes between recording runs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CacheManifest:
    """Metadata stored alongside a recorded fixture.

    Attributes:
        version: Manifest format version (currently ``1``).
        connector: Name of the connector that produced this fixture.
        phase: Test phase that produced the fixture (``"integration"``).
        client: Attribute name of the data client on the connector.
        sdk_version: ``glean-indexing-sdk`` version at record time.
        schema_version: Fixture schema version (increment when NDJSON shape changes).
        recorded_at: ISO-8601 UTC timestamp of the recording run.
        item_count: Number of items written to the NDJSON file.
    """

    version: int = 1
    connector: str = ""
    phase: str = "integration"
    client: str = ""
    sdk_version: str = ""
    schema_version: int = 1
    recorded_at: str = ""
    item_count: int = 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Serialise the manifest to *path* as JSON.

        Args:
            path: Destination file path (``manifest.json``).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "CacheManifest":
        """Deserialise a manifest from *path*.

        Args:
            path: Source file path (``manifest.json``).

        Returns:
            A populated :class:`CacheManifest` instance.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        data = json.loads(path.read_text())
        # Strip unknown keys so old manifests don't break new code.
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    # ------------------------------------------------------------------
    # Staleness check
    # ------------------------------------------------------------------

    def is_stale(self, current_sdk_version: str) -> bool:
        """Return ``True`` if the fixture should be re-recorded.

        A fixture is stale when the SDK version at record time differs from
        *current_sdk_version*, meaning the data shape may have changed.

        Args:
            current_sdk_version: The SDK version running now (from importlib.metadata).

        Returns:
            ``True`` if re-recording is needed; ``False`` otherwise.
        """
        return self.sdk_version != current_sdk_version

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        connector: str,
        client: str,
        sdk_version: str,
        item_count: int,
        phase: str = "integration",
        schema_version: int = 1,
    ) -> "CacheManifest":
        """Build a fresh manifest ready to be saved.

        Args:
            connector: Connector name.
            client: Data-client attribute name.
            sdk_version: Running SDK version.
            item_count: Number of items in the corresponding NDJSON file.
            phase: Test phase label.
            schema_version: Schema version for the NDJSON payload.

        Returns:
            A populated :class:`CacheManifest`.
        """
        return cls(
            connector=connector,
            phase=phase,
            client=client,
            sdk_version=sdk_version,
            schema_version=schema_version,
            recorded_at=datetime.now(tz=timezone.utc).isoformat(),
            item_count=item_count,
        )
