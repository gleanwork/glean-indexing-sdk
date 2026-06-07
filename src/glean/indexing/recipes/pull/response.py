"""Response wrapper for source-side HTTP pull recipes."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PullResponse:
    """Parsed source API response."""

    status_code: int
    headers: dict[str, str]
    url: str
    data: Any = None
    content: bytes | None = None

    def json_dict(self) -> dict[str, Any]:
        """Return parsed JSON data as a dictionary."""
        if isinstance(self.data, dict):
            return self.data
        msg = f"Expected JSON object, got {type(self.data).__name__}"
        raise TypeError(msg)

    def json_list(self) -> list[Any]:
        """Return parsed JSON data as a list."""
        if isinstance(self.data, list):
            return self.data
        msg = f"Expected JSON list, got {type(self.data).__name__}"
        raise TypeError(msg)
