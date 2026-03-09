"""
Validates the SDK worker's protocol messages against the published
Glean Connector Worker Protocol schema.

Schema: https://gleanwork.github.io/connector-mcp/protocol/v1.0.json

This test fetches the live schema so it always runs against the
published contract — not a vendored copy that could drift.
"""

import json
import urllib.request

import pytest

SCHEMA_URL = "https://gleanwork.github.io/connector-mcp/protocol/v1.0.json"


@pytest.fixture(scope="module")
def protocol_schema():
    """Fetch the live protocol schema from GitHub Pages."""
    try:
        with urllib.request.urlopen(SCHEMA_URL, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        pytest.skip(f"Could not fetch protocol schema from {SCHEMA_URL}: {e}")


def validate(schema_doc, definition_name, message):
    """Validate a message against a named definition in the schema."""
    import jsonschema

    definition = schema_doc["definitions"][definition_name]
    jsonschema.validate(message, definition)


@pytest.mark.unit
class TestExecuteResponse:
    def test_valid_response_conforms_to_schema(self, protocol_schema):
        validate(
            protocol_schema,
            "ExecuteResponse",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"execution_id": "exec-123", "status": "started"},
            },
        )

    def test_missing_execution_id_fails(self, protocol_schema):
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            validate(
                protocol_schema,
                "ExecuteResponse",
                {"jsonrpc": "2.0", "id": 1, "result": {"status": "started"}},
            )


@pytest.mark.unit
class TestRecordFetchedNotification:
    def test_valid_notification_conforms_to_schema(self, protocol_schema):
        from glean.indexing.worker.protocol import RecordFetchedNotification

        notification = RecordFetchedNotification(
            record_id="r-0",
            index=0,
            data={"id": "KB-001", "title": "Getting Started"},
        )
        message = notification.to_notification().model_dump(exclude_none=True)
        validate(protocol_schema, "RecordFetchedNotification", message)

    def test_old_record_method_fails_schema(self, protocol_schema):
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            validate(
                protocol_schema,
                "RecordFetchedNotification",
                {"method": "record", "params": {"id": "1", "title": "T"}},
            )


@pytest.mark.unit
class TestExecutionCompleteNotification:
    def test_valid_success_notification_conforms_to_schema(self, protocol_schema):
        from glean.indexing.worker.protocol import ExecutionCompleteNotification

        notification = ExecutionCompleteNotification(
            execution_id="exec-123",
            success=True,
            total_records=5,
            successful_records=5,
            failed_records=0,
            total_duration_ms=1234.5,
        )
        message = notification.to_notification().model_dump(exclude_none=True)
        validate(protocol_schema, "ExecutionCompleteNotification", message)

    def test_valid_failure_notification_conforms_to_schema(self, protocol_schema):
        from glean.indexing.worker.protocol import ExecutionCompleteNotification

        notification = ExecutionCompleteNotification(
            execution_id="exec-456",
            success=False,
            total_records=0,
            successful_records=0,
            failed_records=0,
            total_duration_ms=500.0,
            error="Connector class not found",
        )
        message = notification.to_notification().model_dump(exclude_none=True)
        validate(protocol_schema, "ExecutionCompleteNotification", message)
