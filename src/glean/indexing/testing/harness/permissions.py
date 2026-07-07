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
   are *absent* from every document's ACL.

Identities collected
--------------------
- ``user_ids``: ``email`` or ``datasource_user_id`` (whichever is set) from
  ``allowedUsers`` entries.
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
    document.  If any negative identity is found in ``allowedUsers`` or
    ``allowedGroups`` of any document, an :class:`AssertionError` is raised
    with a descriptive message listing the violating identities and the
    document IDs where they appear.

    Args:
        documents: Transformed documents to inspect.
        negative_test_identities: Identities that must be absent from all ACLs.

    Raises:
        AssertionError: If any negative identity appears in any document's ACL.
    """
    if not negative_test_identities:
        return

    negative_set = set(negative_test_identities)
    violations: dict[str, list[str]] = {}  # identity → list of document IDs

    for doc in documents:
        perms = doc.permissions
        if perms is None:
            continue

        doc_id = doc.id or "<unknown>"
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

    if violations:
        details = "; ".join(
            f"{identity!r} in docs {doc_ids}" for identity, doc_ids in sorted(violations.items())
        )
        raise AssertionError(
            f"Identities listed in negative_test_identities appear in document permission "
            f"payloads: {details}"
        )
