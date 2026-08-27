"""Permission-reference extraction and negative-identity assertion helpers.

``extract_permission_refs`` walks a list of transformed
:class:`~glean.api_client.models.DocumentDefinition` objects and collects every
user and group identity referenced in their ACL payloads.  This is used in two
ways:

1. **Targeted identity indexing (Phase 2 / Phase 3)**: index only the users and
   groups that actually appear in the crawled document set — avoids broken
   permission graphs from partial identity crawls.

2. **Negative permission assertions (Phase 2)**: verify that identities listed
   in :attr:`~glean.indexing.testing.harness.config.TestConfig.negative_test_identities`
   cannot access any document through literal ACL entries or broad-access settings.

Identities collected
--------------------
- ``user_ids``: email is preferred; ``datasource_user_id`` is used as
  fallback when ``email`` is not set on a ``UserReferenceDefinition``.
- ``group_ids``: every string from ``allowedGroups`` and from each
  ``allowedGroupIntersections[*].requiredGroups`` entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from glean.api_client.models import DocumentDefinition


@dataclass
class PermissionRefs:
    """Identity references extracted from a set of transformed documents.

    Attributes:
        user_ids: Unique set of user identifiers (email or datasource user ID).
        group_ids: Unique set of group name strings.
    """

    user_ids: Set[str] = field(default_factory=set)
    group_ids: Set[str] = field(default_factory=set)


def extract_permission_refs(documents: List[DocumentDefinition]) -> PermissionRefs:
    """Walk ``allowedUsers`` and ``allowedGroups`` of each document.

    Collects all user and group identities referenced in permission payloads.
    Documents without a ``permissions`` block, or with ``None``-valued fields,
    are silently skipped.

    Args:
        documents: List of transformed :class:`~glean.api_client.models.DocumentDefinition`
            objects (e.g. ``mock_client.documents_posted``).

    Returns:
        A :class:`PermissionRefs` containing deduplicated identity sets.
    """
    refs = PermissionRefs()

    for doc in documents:
        perms = doc.permissions
        if perms is None:
            continue

        # Collect user references — prefer email, fall back to datasource_user_id
        for user_ref in perms.allowed_users or []:
            identity = user_ref.email or user_ref.datasource_user_id
            if identity:
                refs.user_ids.add(identity)

        # allowedGroups is List[str]
        for group in perms.allowed_groups or []:
            if group:
                refs.group_ids.add(group)

        # allowedGroupIntersections — each intersection has requiredGroups: List[str]
        for intersection in perms.allowed_group_intersections or []:
            for group in intersection.required_groups or []:
                if group:
                    refs.group_ids.add(group)

    return refs


def assert_negative_identities_absent(
    documents: List[DocumentDefinition],
    negative_test_identities: List[str],
) -> None:
    """Assert that none of the *negative_test_identities* appear in any document's ACL.

    A "negative identity" is one that must NOT have access to any crawled
    document. The check covers all three literal ACL fields on each document:

    - ``allowedUsers`` (email preferred over ``datasource_user_id``)
    - ``allowedGroups`` (list of group name strings)
    - ``allowedGroupIntersections[*].requiredGroups``

    The check also fails conservatively for documents without a ``permissions``
    block and documents with ``allowAnonymousAccess`` or
    ``allowAllDatasourceUsersAccess`` enabled. In those cases, absence of access
    for the configured identities cannot be established.

    All literal and broad-access violations are aggregated into one descriptive
    :class:`AssertionError` that identifies the affected documents.

    Args:
        documents: Transformed documents to inspect.
        negative_test_identities: Identities that must not have access to any document.

    Raises:
        AssertionError: If a negative identity appears in a literal ACL, or if
            missing or broad permissions prevent proving that it has no access.
    """
    if not negative_test_identities:
        return

    negative_set = set(negative_test_identities)
    violations: dict[str, list[str]] = {}  # identity → list of document IDs
    broad_access_violations: list[str] = []

    for doc in documents:
        perms = doc.permissions
        doc_id = doc.id or "<unknown>"
        if perms is None:
            broad_access_violations.append(
                f"{doc_id!r} (permissions=None; absence cannot be established)"
            )
            continue
        if perms.allow_anonymous_access is True:
            broad_access_violations.append(
                f"{doc_id!r} (allow_anonymous_access=True; broad access may include negative identities)"
            )
        if perms.allow_all_datasource_users_access is True:
            broad_access_violations.append(
                f"{doc_id!r} (allow_all_datasource_users_access=True; broad access may include negative identities)"
            )

        present_in_doc: Set[str] = set()

        for user_ref in perms.allowed_users or []:
            identity = user_ref.email or user_ref.datasource_user_id
            if identity and identity in negative_set:
                present_in_doc.add(identity)

        for group in perms.allowed_groups or []:
            if group and group in negative_set:
                present_in_doc.add(group)

        for intersection in perms.allowed_group_intersections or []:
            for group in intersection.required_groups or []:
                if group and group in negative_set:
                    present_in_doc.add(group)

        for identity in present_in_doc:
            violations.setdefault(identity, []).append(doc_id)

    messages: list[str] = []
    if violations:
        details = "; ".join(
            f"{identity!r} in docs {doc_ids}" for identity, doc_ids in sorted(violations.items())
        )
        messages.append(
            f"Identities listed in negative_test_identities appear in document permission "
            f"payloads: {details}"
        )
    if broad_access_violations:
        messages.append(
            "Negative identity absence cannot be established for documents: "
            + "; ".join(broad_access_violations)
        )
    if messages:
        raise AssertionError("\n".join(messages))
