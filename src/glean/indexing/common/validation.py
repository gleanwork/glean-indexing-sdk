"""Validation for contracts enforced by the Glean Indexing API."""

import re

_DATASOURCE_NAME_PATTERN = re.compile(r"[A-Za-z0-9]+")


def validate_datasource_name_for_configuration(name: str) -> None:
    """Validate a datasource name before creating or updating its configuration.

    Datasource references used for reads are intentionally not validated here so
    existing or server-normalized names remain addressable.
    """
    if _DATASOURCE_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError(f"Datasource name {name!r} is invalid; use only ASCII letters and digits.")
