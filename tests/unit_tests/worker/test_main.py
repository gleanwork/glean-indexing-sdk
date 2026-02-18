"""Tests for StdioWorkerServer transport layer."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from glean.indexing.worker.main import StdioWorkerServer
from glean.indexing.worker.protocol import (
    JsonRpcNotification,
    JsonRpcResponse,
)

# --- stdout helpers ---


class TestWriteMessage:
    """Tests for StdioWorkerServer.write_message."""

    def test_write_message(self, tmp_path: Path):
        """Test that write_message writes JSON followed by newline."""
        server = StdioWorkerServer(tmp_path)
        buf = StringIO()
        with patch("sys.stdout", buf):
            server.write_message({"jsonrpc": "2.0", "id": 1, "result": "ok"})

        output = buf.getvalue()
        assert output.endswith("\n")
        parsed = json.loads(output.strip())
        assert parsed["id"] == 1
        assert parsed["result"] == "ok"

    def test_emit_notification(self, tmp_path: Path):
        """Test that emit_notification serialises a JsonRpcNotification."""
        server = StdioWorkerServer(tmp_path)
        buf = StringIO()
        notification = JsonRpcNotification(method="log", params={"level": "info", "message": "hi"})
        with patch("sys.stdout", buf):
            server.emit_notification(notification)

        parsed = json.loads(buf.getvalue().strip())
        assert parsed["method"] == "log"
        assert parsed["params"]["message"] == "hi"

    def test_send_response(self, tmp_path: Path):
        """Test that send_response serialises a JsonRpcResponse."""
        server = StdioWorkerServer(tmp_path)
        buf = StringIO()
        response = JsonRpcResponse.success(42, {"status": "ok"})
        with patch("sys.stdout", buf):
            server.send_response(response)

        parsed = json.loads(buf.getvalue().strip())
        assert parsed["id"] == 42
        assert parsed["result"]["status"] == "ok"
        assert "error" not in parsed


# --- _check_parent_alive ---


class TestCheckParentAlive:
    """Tests for StdioWorkerServer._check_parent_alive."""

    def test_same_ppid(self, tmp_path: Path):
        """Test returns True when parent pid unchanged."""
        server = StdioWorkerServer(tmp_path)
        assert server._check_parent_alive() is True

    def test_changed_ppid(self, tmp_path: Path):
        """Test returns False when parent pid changed (orphaned)."""
        server = StdioWorkerServer(tmp_path)
        # Simulate parent dying by changing the stored ppid
        server._parent_pid = -999
        assert server._check_parent_alive() is False
