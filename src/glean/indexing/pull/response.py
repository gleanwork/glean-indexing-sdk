"""Response wrappers for source-side HTTP calls."""

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
        """Return JSON data as a dictionary."""
        if isinstance(self.data, dict):
            return self.data
        raise TypeError(f"Expected JSON object response, got {type(self.data).__name__}")

    def json_list(self) -> list[Any]:
        """Return JSON data as a list."""
        if isinstance(self.data, list):
            return self.data
        raise TypeError(f"Expected JSON list response, got {type(self.data).__name__}")
