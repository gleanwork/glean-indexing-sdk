"""Tests for the Glean SDK exception hierarchy."""

import pytest

from glean.indexing.exceptions import (
    GleanConfigurationError,
    GleanError,
    GleanValidationError,
    InconsistentDataError,
    InvalidDatasourceConfigError,
    InvalidPropertyError,
    MissingEnvironmentVariableError,
    UnsupportedConnectorTypeError,
)


class TestGleanError:
    """Tests for the base GleanError class."""

    def test_message_only(self):
        """Test GleanError with just a message."""
        error = GleanError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.fix_suggestion is None
        assert error.docs_url is None
        assert str(error) == "Something went wrong"

    def test_message_with_fix_suggestion(self):
        """Test GleanError with message and fix suggestion."""
        error = GleanError("Something went wrong", fix_suggestion="Try this instead")
        assert error.message == "Something went wrong"
        assert error.fix_suggestion == "Try this instead"
        assert "How to fix: Try this instead" in str(error)

    def test_message_with_docs_url(self):
        """Test GleanError with message and docs URL."""
        error = GleanError("Something went wrong", docs_url="https://docs.example.com")
        assert error.docs_url == "https://docs.example.com"
        assert "Documentation: https://docs.example.com" in str(error)

    def test_full_error_message(self):
        """Test GleanError with all fields."""
        error = GleanError(
            "Something went wrong",
            fix_suggestion="Try this instead",
            docs_url="https://docs.example.com",
        )
        message = str(error)
        assert "Something went wrong" in message
        assert "How to fix: Try this instead" in message
        assert "Documentation: https://docs.example.com" in message


class TestGleanConfigurationError:
    """Tests for GleanConfigurationError."""

    def test_inherits_from_glean_error(self):
        """Test that GleanConfigurationError inherits from GleanError."""
        error = GleanConfigurationError("Config error")
        assert isinstance(error, GleanError)

    def test_inherits_from_value_error(self):
        """Test backward compatibility with ValueError."""
        error = GleanConfigurationError("Config error")
        assert isinstance(error, ValueError)

    def test_can_be_caught_as_value_error(self):
        """Test that the exception can be caught as ValueError."""
        with pytest.raises(ValueError):
            raise GleanConfigurationError("Config error")


class TestMissingEnvironmentVariableError:
    """Tests for MissingEnvironmentVariableError."""

    def test_single_missing_variable(self):
        """Test error message with a single missing variable."""
        error = MissingEnvironmentVariableError(["GLEAN_INSTANCE"])
        assert error.missing_vars == ["GLEAN_INSTANCE"]
        assert "GLEAN_INSTANCE" in str(error)
        assert "export GLEAN_INSTANCE=<value>" in str(error)
        assert error.docs_url == MissingEnvironmentVariableError.DOCS_URL

    def test_multiple_missing_variables(self):
        """Test error message with multiple missing variables."""
        error = MissingEnvironmentVariableError(["GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN"])
        assert error.missing_vars == ["GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN"]
        message = str(error)
        assert "GLEAN_INSTANCE" in message
        assert "GLEAN_INDEXING_API_TOKEN" in message
        assert "export" in message

    def test_inherits_from_configuration_error(self):
        """Test inheritance hierarchy."""
        error = MissingEnvironmentVariableError(["TEST_VAR"])
        assert isinstance(error, GleanConfigurationError)
        assert isinstance(error, GleanError)
        assert isinstance(error, ValueError)


class TestInvalidDatasourceConfigError:
    """Tests for InvalidDatasourceConfigError."""

    def test_missing_field(self):
        """Test error message for missing config field."""
        error = InvalidDatasourceConfigError("name")
        assert error.field_name == "name"
        assert "name" in str(error)
        assert "CustomDatasourceConfig" in str(error)
        assert error.docs_url == InvalidDatasourceConfigError.DOCS_URL

    def test_inherits_from_configuration_error(self):
        """Test inheritance hierarchy."""
        error = InvalidDatasourceConfigError("display_name")
        assert isinstance(error, GleanConfigurationError)
        assert isinstance(error, GleanError)
        assert isinstance(error, ValueError)


class TestGleanValidationError:
    """Tests for GleanValidationError."""

    def test_inherits_from_glean_error(self):
        """Test that GleanValidationError inherits from GleanError."""
        error = GleanValidationError("Validation error")
        assert isinstance(error, GleanError)

    def test_inherits_from_value_error(self):
        """Test backward compatibility with ValueError."""
        error = GleanValidationError("Validation error")
        assert isinstance(error, ValueError)


class TestInvalidPropertyError:
    """Tests for InvalidPropertyError."""

    def test_invalid_property_name(self):
        """Test error message for invalid property."""
        error = InvalidPropertyError("name", "cannot be empty")
        assert error.property_field == "name"
        assert error.reason == "cannot be empty"
        assert "Invalid property 'name': cannot be empty" in str(error)
        assert "Provide a valid value for 'name'" in str(error)

    def test_inherits_from_validation_error(self):
        """Test inheritance hierarchy."""
        error = InvalidPropertyError("test", "test reason")
        assert isinstance(error, GleanValidationError)
        assert isinstance(error, GleanError)
        assert isinstance(error, ValueError)


class TestInconsistentDataError:
    """Tests for InconsistentDataError."""

    def test_basic_inconsistency(self):
        """Test error message for data inconsistency."""
        error = InconsistentDataError("identity data", "Groups provided without memberships")
        assert error.data_type == "identity data"
        assert error.details == "Groups provided without memberships"
        assert "Inconsistent identity data" in str(error)

    def test_with_fix_suggestion(self):
        """Test error message with fix suggestion."""
        error = InconsistentDataError(
            "identity data",
            "Groups provided without memberships",
            fix_suggestion="Provide memberships for all groups",
        )
        assert "How to fix: Provide memberships for all groups" in str(error)

    def test_inherits_from_validation_error(self):
        """Test inheritance hierarchy."""
        error = InconsistentDataError("test", "test details")
        assert isinstance(error, GleanValidationError)
        assert isinstance(error, GleanError)
        assert isinstance(error, ValueError)


class TestUnsupportedConnectorTypeError:
    """Tests for UnsupportedConnectorTypeError."""

    def test_unsupported_type(self):
        """Test error message for unsupported connector type."""

        class FakeConnector:
            pass

        class SupportedConnector:
            pass

        error = UnsupportedConnectorTypeError(FakeConnector, [SupportedConnector])
        assert error.connector_type == FakeConnector
        assert error.supported_types == [SupportedConnector]
        assert "FakeConnector" in str(error)
        assert "SupportedConnector" in str(error)

    def test_multiple_supported_types(self):
        """Test error message with multiple supported types."""

        class FakeConnector:
            pass

        class SupportedA:
            pass

        class SupportedB:
            pass

        error = UnsupportedConnectorTypeError(FakeConnector, [SupportedA, SupportedB])
        message = str(error)
        assert "SupportedA" in message
        assert "SupportedB" in message

    def test_inherits_from_validation_error(self):
        """Test inheritance hierarchy."""

        class FakeConnector:
            pass

        error = UnsupportedConnectorTypeError(FakeConnector, [])
        assert isinstance(error, GleanValidationError)
        assert isinstance(error, GleanError)
        assert isinstance(error, ValueError)


class TestExceptionHierarchyCatchAll:
    """Tests for catching all SDK exceptions with GleanError."""

    def test_catch_all_with_glean_error(self):
        """Test that all SDK exceptions can be caught with GleanError."""
        exceptions = [
            GleanConfigurationError("test"),
            MissingEnvironmentVariableError(["TEST"]),
            InvalidDatasourceConfigError("field"),
            GleanValidationError("test"),
            InvalidPropertyError("field", "reason"),
            InconsistentDataError("type", "details"),
            UnsupportedConnectorTypeError(str, [int]),
        ]

        for exc in exceptions:
            with pytest.raises(GleanError):
                raise exc

    def test_backward_compatible_with_value_error(self):
        """Test that all exceptions can still be caught as ValueError."""
        exceptions = [
            GleanConfigurationError("test"),
            MissingEnvironmentVariableError(["TEST"]),
            InvalidDatasourceConfigError("field"),
            GleanValidationError("test"),
            InvalidPropertyError("field", "reason"),
            InconsistentDataError("type", "details"),
            UnsupportedConnectorTypeError(str, [int]),
        ]

        for exc in exceptions:
            with pytest.raises(ValueError):
                raise exc
