"""Local checkpoint storage for the Webex connector snippet."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileCheckpointStore:
    """File-backed checkpoint store for Webex incremental crawls."""

    path: Path

    def read_last_activity_cursor(self) -> str | None:
        """Read the stored Webex room last-activity cursor."""
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        cursor = data.get("last_activity_cursor")
        return cursor if isinstance(cursor, str) and cursor else None

    def write_last_activity_cursor(self, cursor: str) -> None:
        """Persist the Webex room last-activity cursor."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"last_activity_cursor": cursor}), encoding="utf-8")
