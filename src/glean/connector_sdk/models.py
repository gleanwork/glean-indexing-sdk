"""Data models for the Glean Connector SDK."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class IndexingMode(Enum):
    """Indexing mode for connectors."""
    
    FULL = auto()
    INCREMENTAL = auto()


@dataclass
class DocumentDefinition:
    """Document definition for indexing to Glean."""
    
    id: str
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    container_id: Optional[str] = None
    mime_type: Optional[str] = "text/html"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    permissions: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmployeeDefinition:
    """Employee definition for indexing to Glean."""
    
    id: str
    name: str
    email: Optional[str] = None
    manager_id: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict) 