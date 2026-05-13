"""Tests for the auto-mock client + facade."""

import pytest

from glean.indexing.testing import (
    MockGleanClient,
    StaticDataClient,
    mock_glean_client,
    with_mock_glean_client,
)
from tests.unit_tests.testing._fakes import DatasourceFake, PeopleFake


class TestPassthroughAndTypoDetection:
    def test_indexing_namespace_passes_through(self):
        with mock_glean_client() as client:
            DatasourceFake(
                name="x", data_client=StaticDataClient([{"id": "a", "title": "A"}])
            ).index_data()
        assert client.indexing.documents.bulk_index.call_count == 1

    def test_unknown_facade_attribute_raises(self):
        client = MockGleanClient()
        with pytest.raises(AttributeError, match="has no attribute 'documnts_posted'"):
            _ = client.documnts_posted

    def test_deep_namespace_typo_raises(self):
        client = MockGleanClient()
        with pytest.raises(AttributeError, match="bluk_index"):
            _ = client.indexing.documents.bluk_index

    def test_dir_includes_facade_methods(self):
        client = MockGleanClient()
        names = dir(client)
        assert "assert_documents_posted" in names
        assert "documents_posted" in names
        assert "indexing" in names


class TestDocumentsAssertions:
    def test_documents_posted_flattens_across_batches(self):
        items = [{"id": str(i), "title": f"Doc {i}"} for i in range(5)]
        connector = DatasourceFake(name="flat", data_client=StaticDataClient(items))
        connector.batch_size = 2
        with mock_glean_client() as client:
            connector.index_data()
        assert len(client.documents_posted) == 5
        assert client.indexing.documents.bulk_index.call_count == 3

    def test_assert_documents_posted_count_matches(self):
        with mock_glean_client() as client:
            DatasourceFake(
                name="c", data_client=StaticDataClient([{"id": "a", "title": "A"}])
            ).index_data()
        client.assert_documents_posted(count=1)

    def test_assert_documents_posted_count_mismatch_message(self):
        with mock_glean_client() as client:
            DatasourceFake(
                name="m", data_client=StaticDataClient([{"id": "a", "title": "A"}])
            ).index_data()
        with pytest.raises(AssertionError, match="Expected 5 documents.*but got 1"):
            client.assert_documents_posted(count=5)

    def test_assert_documents_posted_filters_by_datasource(self):
        item = [{"id": "a", "title": "A"}]
        with mock_glean_client() as client:
            DatasourceFake(name="d1", data_client=StaticDataClient(item)).index_data()
            DatasourceFake(name="d2", data_client=StaticDataClient(item)).index_data()
        client.assert_documents_posted(count=1, datasource="d1")
        client.assert_documents_posted(count=1, datasource="d2")
        client.assert_documents_posted(count=2)

    def test_assert_documents_posted_no_documents_raises(self):
        client = MockGleanClient()
        with pytest.raises(AssertionError, match="at least one"):
            client.assert_documents_posted()


class TestEmployeesAssertions:
    def test_employees_posted_populated(self):
        emps = [{"email": "a@b.com", "first_name": "A", "last_name": "B"}]
        with mock_glean_client() as client:
            PeopleFake(name="p", data_client=StaticDataClient(emps)).index_data()
        assert len(client.employees_posted) == 1
        assert client.employees_posted[0].email == "a@b.com"
        client.assert_employees_posted(count=1)

    def test_assert_employees_posted_mismatch(self):
        client = MockGleanClient()
        with pytest.raises(AssertionError, match="at least one"):
            client.assert_employees_posted()


class TestFreshClientPerEntry:
    def test_each_cm_enter_yields_fresh_client(self):
        with mock_glean_client() as a:
            DatasourceFake(
                name="a", data_client=StaticDataClient([{"id": "1", "title": "T"}])
            ).index_data()
        assert len(a.documents_posted) == 1
        with mock_glean_client() as b:
            pass
        assert len(b.documents_posted) == 0
        assert a is not b


class TestDecorator:
    def test_decorator_injects_client(self):
        @with_mock_glean_client
        def runs(client: MockGleanClient) -> None:
            DatasourceFake(
                name="d", data_client=StaticDataClient([{"id": "a", "title": "A"}])
            ).index_data()
            client.assert_documents_posted(count=1)

        runs()

    def test_decorator_passes_through_args_and_kwargs(self):
        @with_mock_glean_client
        def runs(client: MockGleanClient, x: int, *, y: int) -> int:
            return x + y

        assert runs(2, y=3) == 5


class TestReset:
    def test_reset_clears_call_history(self):
        with mock_glean_client() as client:
            DatasourceFake(
                name="r", data_client=StaticDataClient([{"id": "a", "title": "A"}])
            ).index_data()
            assert len(client.documents_posted) == 1
            client.reset()
            assert len(client.documents_posted) == 0
