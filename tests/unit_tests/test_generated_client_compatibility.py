"""Compatibility checks for generated-client surfaces used by the SDK."""

from inspect import signature

from glean.api_client.people import People


def test_employee_bulk_replacement_surface_is_available() -> None:
    """The constrained generated client must retain full-replacement controls."""
    bulk_index = getattr(People, "bulk_index", None)

    assert callable(bulk_index), "glean-api-client no longer exposes People.bulk_index"
    assert {
        "employees",
        "upload_id",
        "is_first_page",
        "is_last_page",
        "force_restart_upload",
        "disable_stale_data_deletion_check",
    } <= set(signature(bulk_index).parameters)
