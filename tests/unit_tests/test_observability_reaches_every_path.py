"""Every upload path must carry the connector's observability and options.

This is a regression guard, not a unit test of `PushUploader`. `PushUploader`
guards every metric behind `if self.observability:`, so a call site that omits
the argument produces silent no-ops rather than an error — which is how the
users, groups, memberships, and employees paths lost their metrics without any
test noticing.
"""

from unittest.mock import MagicMock, patch


from glean.api_client.models import (
    CustomDatasourceConfig,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
    EmployeeInfoDefinition,
)
from glean.indexing.connectors import BaseDatasourceConnector, BasePeopleConnector
from glean.indexing.models import ConnectorOptions
from glean.indexing.testing import StaticDataClient

CONFIG = CustomDatasourceConfig(name="wiki", display_name="Wiki")

OPTIONS = ConnectorOptions(upload_timeout_ms=1234, upload_max_workers=7)


class EveryEntityConnector(BaseDatasourceConnector):
    """Emits a document plus a full identity set, so every path is exercised."""

    configuration = CONFIG

    def __init__(self):
        super().__init__("wiki", StaticDataClient([{"id": "1"}]))

    def transform(self, data):
        return [DocumentDefinition(datasource="wiki", id="1", title="One")]

    def get_identities(self):
        return {
            "users": [DatasourceUserDefinition(email="a@b.com", name="A")],
            "groups": [DatasourceGroupDefinition(name="g")],
            "memberships": [DatasourceBulkMembershipDefinition(member_user_id="a@b.com")],
        }


class PeopleConnector(BasePeopleConnector):
    configuration = CONFIG

    def __init__(self):
        super().__init__("wiki", StaticDataClient([{"email": "a@b.com"}]))

    def transform(self, data):
        return [EmployeeInfoDefinition(email="a@b.com", department="Eng")]


DATASOURCE_METHODS = (
    "bulk_index_documents",
    "bulk_index_users",
    "bulk_index_groups",
    "bulk_index_memberships",
)


def _uploader_kwargs_per_call(uploader: MagicMock) -> list[dict]:
    """The kwargs each `PushUploader(...)` was constructed with."""
    return [dict(call.kwargs) for call in uploader.call_args_list]


@patch("glean.indexing.connectors.base_datasource_connector.PushUploader")
def test_observability_reaches_every_datasource_upload_path(uploader: MagicMock):
    connector = EveryEntityConnector()
    connector.index_data(options=OPTIONS)

    # Every construction, not only the ones that happen to be wired -- filtering
    # to those would make this assertion vacuously true, which is the same
    # oversight that let the regression through.
    constructions = _uploader_kwargs_per_call(uploader)
    assert constructions, "no PushUploader was constructed at all"
    for kwargs in constructions:
        assert "observability" in kwargs, f"constructed without observability: {kwargs}"
        assert kwargs["observability"] is connector._observability
        assert kwargs["timeout_ms"] == 1234
        assert kwargs["upload_max_workers"] == 7

    missing = [
        name for name in DATASOURCE_METHODS if not getattr(uploader.return_value, name).called
    ]
    assert not missing, f"paths not exercised: {missing}"


@patch("glean.indexing.connectors.base_datasource_connector.PushUploader")
def test_every_datasource_path_is_constructed_the_same_way(uploader: MagicMock):
    """Identical wiring per path, so one call site cannot drift from the others."""
    EveryEntityConnector().index_data(options=OPTIONS)

    shapes = {frozenset(kw) for kw in _uploader_kwargs_per_call(uploader)}
    assert len(shapes) == 1, f"upload paths constructed differently: {shapes}"


@patch("glean.indexing.connectors.base_people_connector.PushUploader")
def test_observability_reaches_the_employees_path(uploader: MagicMock):
    connector = PeopleConnector()
    connector.index_data(options=OPTIONS)

    kwargs = _uploader_kwargs_per_call(uploader)[-1]
    assert kwargs["observability"] is connector._observability
    assert kwargs["upload_max_workers"] == 7
    uploader.return_value.bulk_index_employees.assert_called_once()
