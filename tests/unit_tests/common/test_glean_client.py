"""Tests for the Glean API client helper."""

from unittest.mock import patch

import pytest

from glean.indexing.common.glean_client import DEFAULT_TIMEOUT_MS, api_client
from glean.indexing.exceptions import MissingEnvironmentVariableError


class TestApiClient:
    """Tests for api_client() helper."""

    def test_default_timeout_constant_is_60_seconds(self):
        """Confirm the documented default timeout is 60 seconds."""
        assert DEFAULT_TIMEOUT_MS == 60_000

    @patch.dict(
        "os.environ",
        {"GLEAN_SERVER_URL": "https://example.com", "GLEAN_INDEXING_API_TOKEN": "token"},
        clear=True,
    )
    @patch("glean.indexing.common.glean_client.Glean")
    def test_passes_default_timeout_when_using_server_url(self, mock_glean):
        """api_client() should pass DEFAULT_TIMEOUT_MS to Glean when using server_url."""
        api_client()

        mock_glean.assert_called_once_with(
            api_token="token",
            server_url="https://example.com",
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

    @patch.dict(
        "os.environ",
        {"GLEAN_INSTANCE": "my-instance", "GLEAN_INDEXING_API_TOKEN": "token"},
        clear=True,
    )
    @patch("glean.indexing.common.glean_client.Glean")
    def test_passes_default_timeout_when_using_instance(self, mock_glean):
        """api_client() should pass DEFAULT_TIMEOUT_MS to Glean when using deprecated instance."""
        api_client()

        mock_glean.assert_called_once_with(
            api_token="token",
            instance="my-instance",
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_when_required_env_vars_missing(self):
        """api_client() should raise when required env vars are missing."""
        with pytest.raises(MissingEnvironmentVariableError):
            api_client()
