"""Shared connector construction for local CLI and generated cloud runners."""

from __future__ import annotations

import inspect
from enum import Enum
from typing import Callable, TypeVar, cast

TConnector = TypeVar("TConnector")


class ConnectorConstructionReason(str, Enum):
    """Stable failure reasons used by CLI and deployed error formatters."""

    NOT_CALLABLE = "not_callable"
    REQUIRES_ARGUMENTS = "requires_arguments"
    CONSTRUCTION_FAILED = "construction_failed"
    WRONG_TYPE = "wrong_type"
    MISSING_INDEX_DATA = "missing_index_data"


class ConnectorConstructionError(ValueError):
    """A connector class or factory does not satisfy the construction contract."""

    def __init__(self, reason: ConnectorConstructionReason, message: str):
        super().__init__(message)
        self.reason = reason


def instantiate_connector(
    connector_class: type[TConnector] | Callable[[], TConnector],
    connector_factory: Callable[[], TConnector] | None = None,
) -> TConnector:
    """Construct and validate a connector without exposing constructor secrets.

    Args:
        connector_class: Expected connector class. A legacy zero-argument callable is also
            accepted when no explicit factory is configured.
        connector_factory: Optional zero-argument callable used instead of class construction.

    Returns:
        A connector instance with a callable ``index_data`` method.

    Raises:
        ConnectorConstructionError: If the class/factory contract is invalid or construction fails.
    """
    expected_type = connector_class if isinstance(connector_class, type) else None
    constructor = connector_factory or connector_class
    constructor_name = getattr(constructor, "__name__", type(constructor).__name__)
    constructor_kind = "factory" if connector_factory is not None else "target"
    if not callable(constructor):
        raise ConnectorConstructionError(
            ConnectorConstructionReason.NOT_CALLABLE,
            f"configured connector {constructor_kind} {constructor_name!r} is not callable",
        )

    try:
        signature = inspect.signature(constructor)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        try:
            signature.bind()
        except TypeError:
            guidance = (
                "; configure connector_factory for required dependencies"
                if connector_factory is None
                else ""
            )
            raise ConnectorConstructionError(
                ConnectorConstructionReason.REQUIRES_ARGUMENTS,
                f"connector {constructor_kind} {constructor_name!r} must be callable without "
                f"arguments{guidance}",
            ) from None

    typed_constructor = cast(Callable[[], TConnector], constructor)
    try:
        connector = typed_constructor()
    except SystemExit:
        raise ConnectorConstructionError(
            ConnectorConstructionReason.CONSTRUCTION_FAILED,
            f"connector {constructor_kind} {constructor_name!r} raised SystemExit; exception "
            "text is hidden because connector construction can handle secrets",
        ) from None
    except Exception as exc:
        raise ConnectorConstructionError(
            ConnectorConstructionReason.CONSTRUCTION_FAILED,
            f"connector {constructor_kind} {constructor_name!r} raised {type(exc).__name__}; "
            "exception text is hidden because connector construction can handle secrets",
        ) from None

    if expected_type is not None and not isinstance(connector, expected_type):
        raise ConnectorConstructionError(
            ConnectorConstructionReason.WRONG_TYPE,
            f"connector factory {constructor_name!r} must return an instance of "
            f"{expected_type.__name__}",
        )
    if not callable(getattr(connector, "index_data", None)):
        class_name = (
            expected_type.__name__ if expected_type is not None else type(connector).__name__
        )
        raise ConnectorConstructionError(
            ConnectorConstructionReason.MISSING_INDEX_DATA,
            f"connector class {class_name!r} has no index_data method",
        )
    return connector
