"""Connector construction contract shared by local and deployed execution."""

from typing import Callable, cast

import pytest

from glean.indexing.deployment.bootstrap import (
    ConnectorConstructionError,
    instantiate_connector,
)


class NeedsArguments:
    def __init__(self, name: str):
        self.name = name

    def index_data(self, mode=None):
        pass


def test_factory_constructs_connector_with_required_arguments():
    def create_connector():
        return NeedsArguments("wiki")

    connector = instantiate_connector(NeedsArguments, create_connector)

    assert connector.name == "wiki"


def test_legacy_zero_argument_class_remains_supported():
    class LegacyConnector:
        def index_data(self, mode=None):
            pass

    assert isinstance(instantiate_connector(LegacyConnector), LegacyConnector)


def test_legacy_callable_target_remains_supported():
    class LegacyConnector:
        def index_data(self, mode=None):
            pass

    def create_connector():
        return LegacyConnector()

    assert isinstance(instantiate_connector(create_connector), LegacyConnector)


def test_callable_without_introspectable_signature_is_invoked():
    class LegacyConnector:
        def index_data(self, mode=None):
            pass

    class NoSignatureFactory:
        __signature__ = object()

        def __call__(self):
            return LegacyConnector()

    assert isinstance(instantiate_connector(NoSignatureFactory()), LegacyConnector)


def test_factory_must_be_callable_without_arguments():
    def create_connector(required):
        return NeedsArguments(required)

    with pytest.raises(ConnectorConstructionError, match="without arguments"):
        instantiate_connector(
            NeedsArguments,
            cast(Callable[[], NeedsArguments], create_connector),
        )


def test_factory_must_return_configured_class():
    class DifferentConnector:
        def index_data(self, mode=None):
            pass

    with pytest.raises(ConnectorConstructionError, match="NeedsArguments"):
        instantiate_connector(NeedsArguments, DifferentConnector)


def test_factory_system_exit_does_not_leak_exception_text():
    def create_connector():
        raise SystemExit("source-secret-token")

    with pytest.raises(ConnectorConstructionError) as excinfo:
        instantiate_connector(NeedsArguments, create_connector)

    message = str(excinfo.value)
    assert "SystemExit" in message
    assert "source-secret-token" not in message


def test_factory_failure_reports_type_without_leaking_exception_text():
    def create_connector():
        raise ValueError("invalid credential: source-secret-token")

    with pytest.raises(ConnectorConstructionError) as excinfo:
        instantiate_connector(NeedsArguments, create_connector)

    message = str(excinfo.value)
    assert "create_connector" in message
    assert "ValueError" in message
    assert "source-secret-token" not in message
