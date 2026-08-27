"""Tests for extract_permission_refs and assert_negative_identities_absent."""

import pytest

from glean.api_client.models import (
    ContentDefinition,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    PermissionsGroupIntersectionDefinition,
    UserReferenceDefinition,
)
from glean.indexing.testing.harness.permissions import (
    PermissionRefs,
    assert_negative_identities_absent,
    extract_permission_refs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc(
    doc_id: str,
    *,
    allowed_users: list | None = None,
    allowed_groups: list | None = None,
    allowed_group_intersections: list | None = None,
    allow_anonymous_access: bool | None = None,
    allow_all_datasource_users_access: bool | None = None,
) -> DocumentDefinition:
    perms = None
    if (
        allowed_users is not None
        or allowed_groups is not None
        or allowed_group_intersections is not None
        or allow_anonymous_access is not None
        or allow_all_datasource_users_access is not None
    ):
        perms = DocumentPermissionsDefinition(
            allowed_users=allowed_users,
            allowed_groups=allowed_groups,
            allowed_group_intersections=allowed_group_intersections,
            allow_anonymous_access=allow_anonymous_access,
            allow_all_datasource_users_access=allow_all_datasource_users_access,
        )
    return DocumentDefinition(
        id=doc_id,
        datasource="test_ds",
        title=f"Doc {doc_id}",
        view_url=f"https://example.com/{doc_id}",
        body=ContentDefinition(mime_type="text/plain", text_content="body"),
        permissions=perms,
    )


def _user(
    email: str | None = None, datasource_user_id: str | None = None
) -> UserReferenceDefinition:
    return UserReferenceDefinition(email=email, datasource_user_id=datasource_user_id)


# ---------------------------------------------------------------------------
# extract_permission_refs
# ---------------------------------------------------------------------------


class TestExtractPermissionRefs:
    def test_empty_document_list(self):
        refs = extract_permission_refs([])
        assert refs.user_ids == set()
        assert refs.group_ids == set()

    def test_document_without_permissions(self):
        doc = _doc("no-perms")
        refs = extract_permission_refs([doc])
        assert refs.user_ids == set()
        assert refs.group_ids == set()

    def test_allowed_users_by_email(self):
        doc = _doc("d1", allowed_users=[_user(email="alice@corp.com"), _user(email="bob@corp.com")])
        refs = extract_permission_refs([doc])
        assert refs.user_ids == {"alice@corp.com", "bob@corp.com"}
        assert refs.group_ids == set()

    def test_allowed_users_by_datasource_id(self):
        doc = _doc("d1", allowed_users=[_user(datasource_user_id="U123")])
        refs = extract_permission_refs([doc])
        assert refs.user_ids == {"U123"}

    def test_allowed_users_email_preferred_over_datasource_id(self):
        doc = _doc("d1", allowed_users=[_user(email="alice@corp.com", datasource_user_id="U999")])
        refs = extract_permission_refs([doc])
        assert "alice@corp.com" in refs.user_ids
        assert "U999" not in refs.user_ids

    def test_allowed_groups(self):
        doc = _doc("d1", allowed_groups=["engineering", "design"])
        refs = extract_permission_refs([doc])
        assert refs.group_ids == {"engineering", "design"}

    def test_allowed_group_intersections(self):
        intersection = PermissionsGroupIntersectionDefinition(required_groups=["eng", "us-team"])
        doc = _doc("d1", allowed_group_intersections=[intersection])
        refs = extract_permission_refs([doc])
        assert refs.group_ids == {"eng", "us-team"}

    def test_multiple_documents_deduplicated(self):
        doc1 = _doc("d1", allowed_users=[_user(email="alice@corp.com")], allowed_groups=["eng"])
        doc2 = _doc("d2", allowed_users=[_user(email="alice@corp.com")], allowed_groups=["design"])
        refs = extract_permission_refs([doc1, doc2])
        assert refs.user_ids == {"alice@corp.com"}
        assert refs.group_ids == {"eng", "design"}

    def test_returns_permission_refs_instance(self):
        refs = extract_permission_refs([])
        assert isinstance(refs, PermissionRefs)


# ---------------------------------------------------------------------------
# assert_negative_identities_absent
# ---------------------------------------------------------------------------


class TestAssertNegativeIdentitiesAbsent:
    def test_no_negative_identities_passes(self):
        doc = _doc("d1", allowed_users=[_user(email="alice@corp.com")])
        assert_negative_identities_absent([doc], [])  # should not raise

    def test_negative_identity_absent_passes(self):
        doc = _doc("d1", allowed_users=[_user(email="alice@corp.com")])
        assert_negative_identities_absent([doc], ["denied@corp.com"])  # should not raise

    def test_negative_user_in_allowed_users_raises(self):
        doc = _doc("d1", allowed_users=[_user(email="denied@corp.com")])
        with pytest.raises(AssertionError, match="denied@corp.com"):
            assert_negative_identities_absent([doc], ["denied@corp.com"])

    def test_negative_user_by_datasource_id_raises(self):
        doc = _doc("d1", allowed_users=[_user(datasource_user_id="U_DENIED")])
        with pytest.raises(AssertionError, match="U_DENIED"):
            assert_negative_identities_absent([doc], ["U_DENIED"])

    def test_negative_group_in_allowed_groups_raises(self):
        doc = _doc("d1", allowed_groups=["bad_group", "ok_group"])
        with pytest.raises(AssertionError, match="bad_group"):
            assert_negative_identities_absent([doc], ["bad_group"])

    def test_negative_group_in_intersections_raises(self):
        intersection = PermissionsGroupIntersectionDefinition(required_groups=["restricted_team"])
        doc = _doc("d1", allowed_group_intersections=[intersection])
        with pytest.raises(AssertionError, match="restricted_team"):
            assert_negative_identities_absent([doc], ["restricted_team"])

    def test_error_message_includes_document_id(self):
        doc = _doc("ticket-42", allowed_users=[_user(email="denied@corp.com")])
        with pytest.raises(AssertionError, match="ticket-42"):
            assert_negative_identities_absent([doc], ["denied@corp.com"])

    def test_multiple_violations_all_reported(self):
        doc1 = _doc("d1", allowed_groups=["bad1"])
        doc2 = _doc("d2", allowed_groups=["bad2"])
        with pytest.raises(AssertionError) as exc_info:
            assert_negative_identities_absent([doc1, doc2], ["bad1", "bad2"])
        msg = str(exc_info.value)
        assert "bad1" in msg
        assert "bad2" in msg

    def test_document_without_permissions_raises_with_document_id(self):
        doc = _doc("no-perms")

        with pytest.raises(AssertionError) as exc_info:
            assert_negative_identities_absent([doc], ["any@corp.com"])

        message = str(exc_info.value)
        assert "no-perms" in message
        assert "permissions=None" in message
        assert "absence cannot be established" in message

    def test_anonymous_access_raises_with_document_id_and_flag(self):
        doc = _doc("public-doc", allow_anonymous_access=True)

        with pytest.raises(AssertionError) as exc_info:
            assert_negative_identities_absent([doc], ["denied@corp.com"])

        message = str(exc_info.value)
        assert "public-doc" in message
        assert "allow_anonymous_access=True" in message

    def test_all_datasource_users_access_raises_with_document_id_and_flag(self):
        doc = _doc("datasource-wide-doc", allow_all_datasource_users_access=True)

        with pytest.raises(AssertionError) as exc_info:
            assert_negative_identities_absent([doc], ["denied@corp.com"])

        message = str(exc_info.value)
        assert "datasource-wide-doc" in message
        assert "allow_all_datasource_users_access=True" in message

    def test_false_and_none_broad_access_flags_pass(self):
        docs = [
            _doc("anonymous-false", allow_anonymous_access=False),
            _doc("datasource-users-false", allow_all_datasource_users_access=False),
            _doc("flags-none", allowed_users=[]),
        ]

        assert_negative_identities_absent(docs, ["denied@corp.com"])

    def test_literal_and_broad_access_violations_across_documents_are_aggregated(self):
        docs = [
            _doc("literal-doc", allowed_users=[_user(email="denied@corp.com")]),
            _doc("no-permissions-doc"),
            _doc("anonymous-doc", allow_anonymous_access=True),
            _doc("datasource-users-doc", allow_all_datasource_users_access=True),
        ]

        with pytest.raises(AssertionError) as exc_info:
            assert_negative_identities_absent(docs, ["denied@corp.com"])

        message = str(exc_info.value)
        assert "'denied@corp.com' in docs ['literal-doc']" in message
        assert "'no-permissions-doc' (permissions=None" in message
        assert "'anonymous-doc' (allow_anonymous_access=True" in message
        assert "'datasource-users-doc' (allow_all_datasource_users_access=True" in message
