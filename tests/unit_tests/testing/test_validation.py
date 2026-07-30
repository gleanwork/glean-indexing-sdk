"""Tests for deterministic connector output validation."""

import pytest

from glean.api_client.models import DocumentDefinition, ObjectDefinition
from glean.indexing.models import CustomDatasourceConfig
from glean.indexing.testing import (
    ConnectorOutputValidationError,
    StaticDataClient,
    validate_connector_output,
)
from tests.unit_tests.testing._fakes import DatasourceFake


class TypedDatasourceFake(DatasourceFake):
    configuration = CustomDatasourceConfig(
        name="typed",
        display_name="Typed",
        object_definitions=[
            ObjectDefinition(name="Article"),
            ObjectDefinition(name="Category"),
            ObjectDefinition(name="Unused"),
        ],
    )


def _document(
    *,
    object_type: str | None = None,
    container_object_type: str | None = None,
) -> DocumentDefinition:
    return DocumentDefinition(
        datasource="typed",
        id="doc-1",
        title="Document",
        object_type=object_type,
        container_object_type=container_object_type,
    )


def test_declared_document_and_container_types_pass():
    connector = TypedDatasourceFake(name="typed", data_client=StaticDataClient([]))

    validate_connector_output(
        connector,
        [_document(object_type="Article", container_object_type="Category")],
    )


def test_unused_configured_object_definitions_are_allowed():
    connector = TypedDatasourceFake(name="typed", data_client=StaticDataClient([]))

    validate_connector_output(connector, [_document(object_type="Article")])


def test_undeclared_document_type_fails_with_actionable_error():
    connector = TypedDatasourceFake(name="typed", data_client=StaticDataClient([]))

    with pytest.raises(
        ConnectorOutputValidationError,
        match=r"Add matching ObjectDefinition entries for: 'Comment'",
    ):
        validate_connector_output(connector, [_document(object_type="Comment")])


def test_undeclared_container_type_fails_with_field_and_document():
    connector = TypedDatasourceFake(name="typed", data_client=StaticDataClient([]))

    with pytest.raises(
        ConnectorOutputValidationError,
        match=r"container_object_type on document 'doc-1'",
    ):
        validate_connector_output(
            connector,
            [_document(object_type="Article", container_object_type="Space")],
        )


def test_empty_document_output_passes():
    connector = TypedDatasourceFake(name="typed", data_client=StaticDataClient([]))

    validate_connector_output(connector, [])
