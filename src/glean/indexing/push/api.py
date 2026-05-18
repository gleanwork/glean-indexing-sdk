"""Stable SDK wrapper around generated Glean indexing API calls."""

from typing import Any, Optional, Sequence

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition
from glean.indexing.push.options import PushOptions


class GleanPushApi:
    """Small facade over the generated Glean client indexing namespace."""

    def __init__(self, client: Any):
        """Initialize the facade with a generated Glean client instance."""
        self._client = client

    def index_documents(
        self,
        *,
        datasource: str,
        documents: Sequence[DocumentDefinition],
        upload_id: Optional[str] = None,
        options: PushOptions,
    ) -> None:
        """Upsert one or more documents through `indexdocuments`."""
        self._client.indexing.documents.index(
            datasource=datasource,
            documents=list(documents),
            upload_id=upload_id,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def bulk_index_documents(
        self,
        *,
        datasource: str,
        documents: Sequence[DocumentDefinition],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
    ) -> None:
        """Upload a page through `bulkindexdocuments`."""
        self._client.indexing.documents.bulk_index(
            datasource=datasource,
            documents=list(documents),
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            force_restart_upload=True if (options.force_restart and is_first_page) else None,
            disable_stale_document_deletion_check=True
            if (options.disable_stale_deletion_check and is_last_page)
            else None,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def delete_document(
        self,
        *,
        datasource: str,
        object_type: str,
        id: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Delete a document."""
        self._client.indexing.documents.delete(
            datasource=datasource,
            object_type=object_type,
            id=id,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def update_permissions(
        self,
        *,
        datasource: str,
        permissions: Any,
        options: PushOptions,
        object_type: Optional[str] = None,
        id: Optional[str] = None,
        view_url: Optional[str] = None,
    ) -> None:
        """Update permissions for a document identified by ID or view URL."""
        self._client.indexing.permissions.update_permissions(
            datasource=datasource,
            permissions=permissions,
            object_type=object_type,
            id=id,
            view_url=view_url,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def index_user(
        self, *, datasource: str, user: Any, options: PushOptions, version: Optional[int] = None
    ) -> None:
        """Index a datasource user."""
        self._client.indexing.permissions.index_user(
            datasource=datasource,
            user=user,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def bulk_index_users(
        self,
        *,
        datasource: str,
        users: Sequence[Any],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
    ) -> None:
        """Upload a page of datasource users."""
        self._client.indexing.permissions.bulk_index_users(
            datasource=datasource,
            users=list(users),
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            force_restart_upload=True if (options.force_restart and is_first_page) else None,
            disable_stale_data_deletion_check=True
            if (options.disable_stale_deletion_check and is_last_page)
            else None,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def delete_user(
        self, *, datasource: str, email: str, options: PushOptions, version: Optional[int] = None
    ) -> None:
        """Delete a datasource user."""
        self._client.indexing.permissions.delete_user(
            datasource=datasource,
            email=email,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def index_group(
        self, *, datasource: str, group: Any, options: PushOptions, version: Optional[int] = None
    ) -> None:
        """Index a datasource group."""
        self._client.indexing.permissions.index_group(
            datasource=datasource,
            group=group,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def bulk_index_groups(
        self,
        *,
        datasource: str,
        groups: Sequence[Any],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
    ) -> None:
        """Upload a page of datasource groups."""
        self._client.indexing.permissions.bulk_index_groups(
            datasource=datasource,
            groups=list(groups),
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            force_restart_upload=True if (options.force_restart and is_first_page) else None,
            disable_stale_data_deletion_check=True
            if (options.disable_stale_deletion_check and is_last_page)
            else None,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def delete_group(
        self,
        *,
        datasource: str,
        group_name: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource group."""
        self._client.indexing.permissions.delete_group(
            datasource=datasource,
            group_name=group_name,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def index_membership(
        self,
        *,
        datasource: str,
        membership: Any,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Index a datasource membership."""
        self._client.indexing.permissions.index_membership(
            datasource=datasource,
            membership=membership,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def bulk_index_memberships(
        self,
        *,
        datasource: str,
        memberships: Sequence[Any],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
        group: Optional[str] = None,
    ) -> None:
        """Upload a page of datasource memberships."""
        self._client.indexing.permissions.bulk_index_memberships(
            datasource=datasource,
            memberships=list(memberships),
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            force_restart_upload=True if (options.force_restart and is_first_page) else None,
            group=group,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def delete_membership(
        self,
        *,
        datasource: str,
        membership: Any,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource membership."""
        self._client.indexing.permissions.delete_membership(
            datasource=datasource,
            membership=membership,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def index_employee(
        self,
        *,
        employee: EmployeeInfoDefinition,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Index one employee."""
        self._client.indexing.people.index(
            employee=employee,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def bulk_index_employees(
        self,
        *,
        employees: Sequence[EmployeeInfoDefinition],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
    ) -> None:
        """Upload a page of employees."""
        self._client.indexing.people.bulk_index(
            employees=list(employees),
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            force_restart_upload=True if (options.force_restart and is_first_page) else None,
            disable_stale_data_deletion_check=True
            if (options.disable_stale_deletion_check and is_last_page)
            else None,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )

    def delete_employee(
        self,
        *,
        employee_email: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> None:
        """Delete an employee."""
        self._client.indexing.people.delete(
            employee_email=employee_email,
            version=version,
            retries=options.retries,
            timeout_ms=options.upload_timeout_ms,
        )
