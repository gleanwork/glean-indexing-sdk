"""Auto-mock helpers for the Glean indexing client.

This module provides:

- :class:`MockGleanClient` — a recording facade wrapping `MagicMock(spec=Glean)`.
  Adds domain-specific assertions (`assert_documents_posted`, etc.) on top of
  the real Speakeasy-generated client surface, so tests stay readable while
  signatures stay automatically in sync with the SDK.
- :func:`mock_glean_client` — context manager factory that patches every
  `api_client` import site in :data:`_PATCH_TARGETS` and yields a fresh
  `MockGleanClient` for the duration of the `with` block.
- :func:`with_mock_glean_client` — decorator form; injects the client as the
  first positional arg of the wrapped function.

The facade only allows attribute access through to the underlying mock for a
whitelisted set of generated SDK namespaces. Anything else raises
`AttributeError`, so typos like `client.documnts_posted` fail loudly instead
of silently creating an auto-mock.
"""

import functools
from contextlib import ExitStack
from types import TracebackType
from typing import Any, Callable, Concatenate, FrozenSet, List, Optional, ParamSpec, Type, TypeVar
from unittest.mock import MagicMock, create_autospec, patch

from glean.api_client import Glean
from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition

from glean.indexing.testing._patch_targets import _PATCH_TARGETS, validate_patch_targets

_P = ParamSpec("_P")
_R = TypeVar("_R")

_ALLOWED_PASSTHROUGH: FrozenSet[str] = frozenset({"indexing", "troubleshooting"})

_glean_spec: Optional[Glean] = None


def _get_glean_spec() -> Glean:
    """Return a cached `Glean` instance used as the `spec=` for the mock.

    The Speakeasy-generated `Glean` class builds its `indexing` namespace
    (and downstream `documents`, `people`, `permissions`, etc.) inside
    `__init__`, not as class attributes. Specing against the *class* would
    therefore reject any attribute access through the namespace tree.
    Specing against a constructed *instance* gives us the full runtime
    attribute set, so typos like `client.indexing.documents.bluk_index`
    raise `AttributeError` while real calls pass through.
    """
    global _glean_spec
    if _glean_spec is None:
        _glean_spec = Glean(api_token="mock-token", instance="mock-instance")
    return _glean_spec


def _flatten_kwarg(call_args_list: Any, key: str) -> List[Any]:
    """Concatenate `call.kwargs[key]` across every recorded call.

    Returns an empty list if no calls captured the given kwarg.
    """
    out: List[Any] = []
    for call in call_args_list:
        items = call.kwargs.get(key)
        if items:
            out.extend(items)
    return out


class MockGleanClient:
    """Recording facade over a `MagicMock(spec=Glean)`.

    Reads the underlying mock's `call_args_list` to expose flattened views of
    what a connector posted (`documents_posted`, `employees_posted`, etc.) and
    convenience `assert_*` methods. The raw mock is reachable via
    `client.indexing.documents.bulk_index` for anything not covered by the
    facade — `spec=Glean` ensures typos in that path also fail loudly.
    """

    def __init__(self) -> None:
        """Create a fresh recording facade."""
        self._mock: MagicMock = create_autospec(_get_glean_spec(), instance=True)

    def __getattr__(self, name: str) -> Any:
        """Forward whitelisted attribute names to the underlying mock.

        Anything outside `_ALLOWED_PASSTHROUGH` raises `AttributeError` so
        typos like `client.documnts_posted` fail loudly.
        """
        if name in _ALLOWED_PASSTHROUGH:
            return getattr(self._mock, name)
        raise AttributeError(
            f"{type(self).__name__} has no attribute {name!r}. "
            f"Did you mean one of {sorted(self._public_names())}? "
            f"For raw client access use `client.indexing.<...>`."
        )

    def __dir__(self) -> List[str]:
        """List facade methods plus whitelisted passthrough names."""
        return sorted(self._public_names() | _ALLOWED_PASSTHROUGH)

    @classmethod
    def _public_names(cls) -> FrozenSet[str]:
        return frozenset(name for name in vars(cls) if not name.startswith("_"))

    @property
    def documents_posted(self) -> List[DocumentDefinition]:
        """All documents passed to `client.indexing.documents.bulk_index` so far.

        Flattened across batches: a connector with `batch_size=2` and 5 docs
        produces a single 5-element list here, not 3 batched lists.
        """
        return _flatten_kwarg(self._mock.indexing.documents.bulk_index.call_args_list, "documents")

    @property
    def employees_posted(self) -> List[EmployeeInfoDefinition]:
        """All employees passed to `client.indexing.people.bulk_index` so far."""
        return _flatten_kwarg(self._mock.indexing.people.bulk_index.call_args_list, "employees")

    @property
    def users_posted(self) -> List[Any]:
        """All users passed to `client.indexing.permissions.bulk_index_users` so far."""
        return _flatten_kwarg(
            self._mock.indexing.permissions.bulk_index_users.call_args_list, "users"
        )

    @property
    def groups_posted(self) -> List[Any]:
        """All groups passed to `client.indexing.permissions.bulk_index_groups` so far."""
        return _flatten_kwarg(
            self._mock.indexing.permissions.bulk_index_groups.call_args_list, "groups"
        )

    @property
    def memberships_posted(self) -> List[Any]:
        """All memberships passed to `client.indexing.permissions.bulk_index_memberships`."""
        return _flatten_kwarg(
            self._mock.indexing.permissions.bulk_index_memberships.call_args_list,
            "memberships",
        )

    def _filtered_count(self, calls: Any, datasource: Optional[str], items_key: str) -> int:
        if datasource is None:
            return sum(len(call.kwargs.get(items_key, [])) for call in calls)
        return sum(
            len(call.kwargs.get(items_key, []))
            for call in calls
            if call.kwargs.get("datasource") == datasource
        )

    def assert_documents_posted(
        self,
        count: Optional[int] = None,
        datasource: Optional[str] = None,
    ) -> None:
        """Assert that documents were posted to `bulk_index`.

        Args:
            count: Expected number of documents. If `None`, asserts at least one.
            datasource: If set, only count documents posted to this datasource.
        """
        actual = self._filtered_count(
            self._mock.indexing.documents.bulk_index.call_args_list, datasource, "documents"
        )
        _assert_count(actual, count, label="documents", datasource=datasource)

    def assert_employees_posted(self, count: Optional[int] = None) -> None:
        """Assert that employees were posted to `bulk_index`.

        Args:
            count: Expected number of employees. If `None`, asserts at least one.
        """
        actual = sum(
            len(call.kwargs.get("employees", []))
            for call in self._mock.indexing.people.bulk_index.call_args_list
        )
        _assert_count(actual, count, label="employees", datasource=None)

    def assert_users_posted(
        self,
        count: Optional[int] = None,
        datasource: Optional[str] = None,
    ) -> None:
        """Assert that users were posted to `bulk_index_users`.

        Args:
            count: Expected number of users. If `None`, asserts at least one.
            datasource: If set, only count users posted to this datasource.
        """
        actual = self._filtered_count(
            self._mock.indexing.permissions.bulk_index_users.call_args_list, datasource, "users"
        )
        _assert_count(actual, count, label="users", datasource=datasource)

    def assert_groups_posted(
        self,
        count: Optional[int] = None,
        datasource: Optional[str] = None,
    ) -> None:
        """Assert that groups were posted to `bulk_index_groups`.

        Args:
            count: Expected number of groups. If `None`, asserts at least one.
            datasource: If set, only count groups posted to this datasource.
        """
        actual = self._filtered_count(
            self._mock.indexing.permissions.bulk_index_groups.call_args_list, datasource, "groups"
        )
        _assert_count(actual, count, label="groups", datasource=datasource)

    def assert_memberships_posted(
        self,
        count: Optional[int] = None,
        datasource: Optional[str] = None,
    ) -> None:
        """Assert that memberships were posted to `bulk_index_memberships`.

        Args:
            count: Expected number of memberships. If `None`, asserts at least one.
            datasource: If set, only count memberships posted to this datasource.
        """
        actual = self._filtered_count(
            self._mock.indexing.permissions.bulk_index_memberships.call_args_list,
            datasource,
            "memberships",
        )
        _assert_count(actual, count, label="memberships", datasource=datasource)

    def assert_datasource_configured(self, name: Optional[str] = None) -> None:
        """Assert that `client.indexing.datasources.add` was called.

        Args:
            name: If set, require at least one call whose payload's `name` equals this.
        """
        calls = self._mock.indexing.datasources.add.call_args_list
        if not calls:
            raise AssertionError("Expected datasource configuration call, but got none.")
        if name is None:
            return
        for call in calls:
            payload = call.kwargs.get("datasource_config") or (call.args[0] if call.args else None)
            if payload is not None and getattr(payload, "name", None) == name:
                return
        raise AssertionError(
            f"Expected datasource configuration call for {name!r}, but no matching call found."
        )

    def reset(self) -> None:
        """Clear the underlying mock's call history."""
        self._mock.reset_mock()


def _assert_count(
    actual: int, count: Optional[int], *, label: str, datasource: Optional[str]
) -> None:
    suffix = f" (datasource={datasource!r})" if datasource else ""
    if count is None:
        if actual == 0:
            raise AssertionError(
                f"Expected at least one {label} to be posted{suffix}, but got none."
            )
        return
    if actual != count:
        raise AssertionError(f"Expected {count} {label} to be posted{suffix}, but got {actual}.")


class _MockGleanClientPatcher:
    """Context manager that patches every `_PATCH_TARGETS` entry to a shared mock.

    Each `__enter__` call creates a fresh `MockGleanClient`; the corresponding
    `__exit__` unwinds all patches. The recorded call history persists on the
    returned facade for assertions after the `with` block exits.
    """

    def __init__(self) -> None:
        """Initialize an unentered patcher."""
        self._stack: Optional[ExitStack] = None
        self._client: Optional[MockGleanClient] = None

    def __enter__(self) -> MockGleanClient:
        """Patch all targets and return a fresh `MockGleanClient`."""
        validate_patch_targets()
        self._client = MockGleanClient()
        stack = ExitStack()
        try:
            for target in _PATCH_TARGETS:
                patcher = stack.enter_context(patch(target))
                patcher.return_value.__enter__.return_value = self._client._mock
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        return self._client

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Unwind all patches."""
        stack = self._stack
        self._stack = None
        if stack is not None:
            stack.close()


def mock_glean_client() -> _MockGleanClientPatcher:
    """Return a context manager that patches the Glean client surface.

    Use as `with mock_glean_client() as client:` in tests. Each call returns a
    fresh patcher; the yielded `MockGleanClient` is freshly recorded for the
    duration of the block.
    """
    return _MockGleanClientPatcher()


def with_mock_glean_client(
    fn: Callable[Concatenate[MockGleanClient, _P], _R],
) -> Callable[_P, _R]:
    """Decorator that injects a `MockGleanClient` as the first positional arg.

    The wrapped function receives a fresh client per invocation. Patches are
    unwound when the function returns.
    """

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with mock_glean_client() as client:
            return fn(client, *args, **kwargs)

    return wrapper
