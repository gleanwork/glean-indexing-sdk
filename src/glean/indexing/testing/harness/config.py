"""Configuration dataclasses for the Glean connector test harness.

``TestConfig`` drives all three test phases (full mock, integration, end-to-end)
via a YAML file at the connector root.  ``ClientConfig`` controls per-client
options such as item limits.

Typical usage::

    config = TestConfig.from_yaml("testing_config.yaml")
    # or in-process:
    config = TestConfig(cache_dir=".glean_test_cache/", use_cache=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ClientConfig:
    """Per-client configuration for the test harness.

    Attributes:
        max_items: Maximum number of items to fetch/replay for this client.
            Defaults to 5. Set to ``None`` to disable the limit.
    """

    max_items: Optional[int] = 5

    def __post_init__(self) -> None:
        if self.max_items is not None and (type(self.max_items) is not int or self.max_items <= 0):
            raise ValueError("max_items must be a positive integer or None")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConfig":
        """Construct a ``ClientConfig`` from a plain dict."""
        return cls(max_items=data.get("max_items", 5))


@dataclass
class TestConfig:
    """Configuration for the ``TestHarness``.

    Attributes:
        cache_dir: Directory where recorded fixtures are stored.
        use_cache: Whether to replay from cache when available.
        refresh_cache: Force re-recording even when a cache hit exists.
        run_id_prefix: Prefix for upload run IDs in Phase 3 (end-to-end).
        clients: Per-client configuration keyed by client name.
        negative_test_identities: Identities that must NOT appear in any
            transformed document's ``allowedUsers`` or ``allowedGroups``.
            Assertion is performed after Phase 2 transforms complete.
    """

    cache_dir: str = ".glean_test_cache/"
    use_cache: bool = True
    refresh_cache: bool = False
    run_id_prefix: str = "sdk_test"
    clients: Dict[str, ClientConfig] = field(default_factory=dict)
    negative_test_identities: List[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TestConfig":
        """Load ``TestConfig`` from a YAML file.

        The file must have a top-level ``testing:`` key.  All sub-keys are
        optional; missing keys use the dataclass defaults.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            A populated ``TestConfig`` instance.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            KeyError: If the ``testing:`` top-level key is absent.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"TestConfig YAML not found: {path}")

        with path.open() as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict) or "testing" not in raw:
            raise KeyError(
                f"Expected a top-level 'testing:' key in {path}, "
                f"but got keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
            )

        return cls.from_dict(raw["testing"] or {})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestConfig":
        """Construct a ``TestConfig`` from a plain dict.

        Args:
            data: Dict corresponding to the ``testing:`` YAML section.

        Returns:
            A populated ``TestConfig`` instance.
        """
        clients_raw: Dict[str, Any] = data.get("clients") or {}
        clients = {name: ClientConfig.from_dict(cfg or {}) for name, cfg in clients_raw.items()}

        return cls(
            cache_dir=data.get("cache_dir", ".glean_test_cache/"),
            use_cache=data.get("use_cache", True),
            refresh_cache=data.get("refresh_cache", False),
            run_id_prefix=data.get("run_id_prefix", "sdk_test"),
            clients=clients,
            negative_test_identities=list(data.get("negative_test_identities") or []),
        )
