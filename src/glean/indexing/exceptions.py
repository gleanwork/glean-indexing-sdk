"""Custom exceptions for the Glean Indexing SDK.

This module provides a hierarchy of exceptions for the Glean Indexing SDK,
enabling precise error handling and actionable error messages.

Exception Hierarchy:
    GleanError(Exception)
    ├── GleanConfigurationError(GleanError, ValueError)
    │   ├── MissingEnvironmentVariableError
    │   └── InvalidDatasourceConfigError
    └── GleanValidationError(GleanError, ValueError)
        ├── InvalidPropertyError
        ├── InconsistentDataError
        └── UnsupportedConnectorTypeError

All exceptions inherit from ValueError for backward compatibility with
existing error handlers.
"""

from typing import Optional, Sequence, Type


class GleanError(Exception):
    """Base exception for all Glean SDK errors.

    Attributes:
        message: The error message describing what went wrong.
        fix_suggestion: A suggestion for how to fix the error.
        docs_url: A URL to relevant documentation.
    """

    def __init__(
        self,
        message: str,
        fix_suggestion: Optional[str] = None,
        docs_url: Optional[str] = None,
    ) -> None:
        self.message = message
        self.fix_suggestion = fix_suggestion
        self.docs_url = docs_url
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the full error message with fix suggestion and docs URL."""
        parts = [self.message]

        if self.fix_suggestion:
            parts.append(f"\nHow to fix: {self.fix_suggestion}")

        if self.docs_url:
            parts.append(f"\nDocumentation: {self.docs_url}")

        return "".join(parts)


class GleanConfigurationError(GleanError, ValueError):
    """Exception raised for configuration-related errors.

    This includes missing environment variables, invalid configuration
    values, and setup issues.
    """


class MissingEnvironmentVariableError(GleanConfigurationError):
    """Exception raised when required environment variables are missing.

    Attributes:
        missing_vars: List of missing environment variable names.
    """

    DOCS_URL = "https://developers.glean.com/docs/indexing_api/indexing_api_overview#authentication"

    def __init__(self, missing_vars: Sequence[str]) -> None:
        self.missing_vars = list(missing_vars)
        message = f"Missing required environment variables: {', '.join(self.missing_vars)}"
        export_commands = " ".join(f"{var}=<value>" for var in self.missing_vars)
        fix_suggestion = (
            f"Set the following environment variable(s) before running your connector:\n"
            f"  export {export_commands}"
        )
        super().__init__(message, fix_suggestion, self.DOCS_URL)


class InvalidDatasourceConfigError(GleanConfigurationError):
    """Exception raised when datasource configuration is invalid.

    Attributes:
        field_name: The name of the missing or invalid field.
    """

    DOCS_URL = (
        "https://developers.glean.com/docs/indexing_api/custom_datasources/build_custom_datasource"
    )

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name
        message = f"Missing required field '{field_name}' in datasource configuration"
        fix_suggestion = f"Set the '{field_name}' attribute in your CustomDatasourceConfig"
        super().__init__(message, fix_suggestion, self.DOCS_URL)


class GleanValidationError(GleanError, ValueError):
    """Exception raised for validation errors.

    This includes invalid input data, inconsistent state, and other
    validation failures.
    """


class InvalidPropertyError(GleanValidationError):
    """Exception raised when a property definition is invalid.

    Attributes:
        property_field: The name of the property field that is invalid.
        reason: The reason the property is invalid.
    """

    def __init__(self, property_field: str, reason: str) -> None:
        self.property_field = property_field
        self.reason = reason
        message = f"Invalid property '{property_field}': {reason}"
        fix_suggestion = f"Provide a valid value for '{property_field}'"
        super().__init__(message, fix_suggestion)


class InconsistentDataError(GleanValidationError):
    """Exception raised when data is in an inconsistent state.

    This is typically raised when related data items are missing or
    don't match expected patterns.

    Attributes:
        data_type: The type of data that is inconsistent.
        details: Additional details about the inconsistency.
    """

    def __init__(
        self,
        data_type: str,
        details: str,
        fix_suggestion: Optional[str] = None,
    ) -> None:
        self.data_type = data_type
        self.details = details
        message = f"Inconsistent {data_type}: {details}"
        super().__init__(message, fix_suggestion)


class UnsupportedConnectorTypeError(GleanValidationError):
    """Exception raised when an unsupported connector type is used.

    Attributes:
        connector_type: The type of connector that is not supported.
        supported_types: List of supported connector types.
    """

    def __init__(
        self,
        connector_type: Type,
        supported_types: Sequence[Type],
    ) -> None:
        self.connector_type = connector_type
        self.supported_types = list(supported_types)
        type_names = [t.__name__ for t in self.supported_types]
        message = f"Unsupported connector type: {connector_type.__name__}"
        fix_suggestion = f"Use one of the supported connector types: {', '.join(type_names)}"
        super().__init__(message, fix_suggestion)
