"""Deterministic validation for connector output captured by the test runner."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from glean.api_client.models import DocumentDefinition
from glean.indexing.connectors.base_connector import BaseConnector


class ConnectorOutputValidationError(AssertionError):
    """Raised when connector output is inconsistent with its configuration."""


def validate_connector_output(
    connector: BaseConnector[Any, Any],
    documents: Sequence[DocumentDefinition],
) -> None:
    """Validate document object types against the connector datasource configuration."""
    if not documents:
        return

    configuration = getattr(connector, "configuration", None)
    if configuration is None:
        return

    declared_types = {
        definition.name
        for definition in (getattr(configuration, "object_definitions", None) or [])
        if definition.name
    }
    undeclared_uses: dict[str, list[str]] = defaultdict(list)

    for document in documents:
        document_id = document.id or "<missing id>"
        if document.object_type and document.object_type not in declared_types:
            undeclared_uses[document.object_type].append(f"object_type on document {document_id!r}")
        if document.container_object_type and document.container_object_type not in declared_types:
            undeclared_uses[document.container_object_type].append(
                f"container_object_type on document {document_id!r}"
            )

    if not undeclared_uses:
        return

    details = "\n".join(
        f"- {object_type!r}: {', '.join(uses[:3])}"
        for object_type, uses in sorted(undeclared_uses.items())
    )
    missing_types = ", ".join(repr(name) for name in sorted(undeclared_uses))
    raise ConnectorOutputValidationError(
        "Connector output uses object types that are missing from "
        "CustomDatasourceConfig.object_definitions:\n"
        f"{details}\n"
        f"Add matching ObjectDefinition entries for: {missing_types}."
    )
