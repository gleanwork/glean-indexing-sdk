"""Pytest fixtures for the Glean testing helpers.

Users can opt in by importing the fixture into their `conftest.py`:

    from glean.indexing.testing.fixtures import glean_client_mock

Then any test that takes `glean_client_mock` as a parameter receives a fresh
:class:`~glean.indexing.testing.MockGleanClient` for the duration of the test.
"""

from typing import Iterator

import pytest

from glean.indexing.testing.mock_client import MockGleanClient, mock_glean_client


@pytest.fixture
def glean_client_mock() -> Iterator[MockGleanClient]:
    """Yield a fresh `MockGleanClient` for the duration of a test.

    Patches every `api_client` import site so any connector run inside the
    test records its calls onto the yielded client.
    """
    with mock_glean_client() as client:
        yield client
