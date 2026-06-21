"""First-class wrappers for push indexing APIs."""

import time
import uuid
from typing import Any, Callable, Mapping, Optional, Sequence, TypeVar

from glean.api_client.models import (
    CheckDocumentAccessResponse,
    CustomDatasourceConfig,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceMembershipDefinition,
    DatasourceUserDefinition,
    DebugDatasourceStatusResponse,
    DebugDocumentRequest,
    DebugDocumentsResponse,
    DocumentDefinition,
    EmployeeInfoDefinition,
)

from glean.indexing.common import BatchProcessor, DocumentBatchProcessor, api_client
from glean.indexing.common.batch_processor import DEFAULT_DOCUMENT_BATCH_SIZE_BYTES
from glean.indexing.observability import ConnectorObservability

T = TypeVar("T")


class StatusClient:
    """Read-only wrappers for datasource and document status APIs."""

    def __init__(
        self,
        datasource: str,
        *,
        retries: Optional[Any] = None,
        server_url: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        http_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        """Initialize a status client for a datasource."""
        self.datasource = datasource
        self.retries = retries
        self.server_url = server_url
        self.timeout_ms = timeout_ms
        self.http_headers = http_headers

    def get_datasource_status(self) -> DebugDatasourceStatusResponse:
        """Get overall datasource upload and processing status."""
        with api_client() as client:
            return client.indexing.datasource.status(
                datasource=self.datasource,
                **self._request_options(),
            )

    def get_documents_status(
        self,
        documents: Sequence[DebugDocumentRequest],
    ) -> DebugDocumentsResponse:
        """Get upload, indexing, and permission status for documents."""
        with api_client() as client:
            return client.indexing.documents.debug_many(
                datasource=self.datasource,
                debug_documents=list(documents),
                **self._request_options(),
            )

    def check_document_access(
        self,
        *,
        object_type: str,
        document_id: str,
        user_email: str,
    ) -> CheckDocumentAccessResponse:
        """Check whether a user has access to a document."""
        with api_client() as client:
            return client.indexing.documents.check_access(
                datasource=self.datasource,
                object_type=object_type,
                doc_id=document_id,
                user_email=user_email,
                **self._request_options(),
            )

    def _request_options(self) -> dict[str, Any]:
        """Return only generated-client request options explicitly configured."""
        options: dict[str, Any] = {}
        if self.retries is not None:
            options["retries"] = self.retries
        if self.server_url is not None:
            options["server_url"] = self.server_url
        if self.timeout_ms is not None:
            options["timeout_ms"] = self.timeout_ms
        if self.http_headers is not None:
            options["http_headers"] = self.http_headers
        return options


class PushUploader:
    """Thin uploader for push indexing APIs."""

    def __init__(
        self,
        datasource: str,
        *,
        retries: Optional[Any] = None,
        server_url: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        http_headers: Optional[Mapping[str, str]] = None,
        observability: Optional[ConnectorObservability] = None,
    ) -> None:
        """Initialize an uploader for a datasource.

        Args:
            datasource: Datasource name to send with each indexing API call.
            retries: Optional generated-client retry configuration.
            server_url: Optional per-call server URL override.
            timeout_ms: Optional per-call timeout override in milliseconds.
            http_headers: Optional per-call HTTP headers.
            observability: Optional observability instance for upload logs and metrics.
        """
        self.datasource = datasource
        self.retries = retries
        self.server_url = server_url
        self.timeout_ms = timeout_ms
        self.http_headers = http_headers
        self.observability = observability

    def configure_datasource(self, config: CustomDatasourceConfig) -> None:
        """Configure a datasource using `datasources.add()`."""
        # Use attribute access instead of model_dump() because certain
        # pydantic/api-client version combinations return camelCase aliases
        # even with by_alias=False, and datasources.add() expects snake_case.
        kwargs = {
            name: getattr(config, name)
            for name in type(config).model_fields
            if name in config.model_fields_set
        }
        with api_client() as client:
            self._call_api("datasources.add", lambda: client.indexing.datasources.add(**kwargs))

    def index_documents(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: Optional[str] = None,
    ) -> None:
        """Add or update multiple documents using `/indexdocuments`."""
        document_list = list(documents)
        document_ids = [document.id for document in document_list if document.id]
        start_time = time.time()
        if self.observability:
            self.observability.log_document_upload_started(document_ids, upload_id=upload_id)
        with api_client() as client:
            self._call_api(
                "documents.index",
                lambda: client.indexing.documents.index(
                    datasource=self.datasource,
                    documents=document_list,
                    upload_id=upload_id,
                    **self._request_options(),
                ),
            )
        if self.observability:
            self.observability.log_document_upload_completed(
                document_ids,
                duration_ms=self._elapsed_ms(start_time),
                upload_id=upload_id,
            )

    def bulk_index_documents(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: Optional[str] = None,
        batch_size: int = 1000,
        max_batch_bytes: Optional[int] = DEFAULT_DOCUMENT_BATCH_SIZE_BYTES,
        force_restart_upload: Optional[bool] = None,
        disable_stale_document_deletion_check: Optional[bool] = None,
    ) -> None:
        """Replace datasource documents using `/bulkindexdocuments`."""
        document_list = list(documents)
        if not document_list:
            return

        batches = list(
            DocumentBatchProcessor(
                document_list,
                batch_size=batch_size,
                max_batch_bytes=max_batch_bytes,
            )
        )
        if not batches:
            return

        upload_id = self._upload_id(upload_id)
        for i, batch in enumerate(batches):
            is_first_page = i == 0
            is_last_page = i == len(batches) - 1
            self.bulk_index_single_batch_upload(
                documents=list(batch),
                upload_id=upload_id,
                is_first_page=is_first_page,
                is_last_page=is_last_page,
                batch_index=i,
                batch_count=len(batches),
                force_restart_upload=self._first_page_value(force_restart_upload, is_first_page),
                disable_stale_document_deletion_check=self._last_page_value(
                    disable_stale_document_deletion_check, is_last_page
                ),
            )

    def bulk_index_single_batch_upload(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: str,
        is_first_page: Optional[bool] = None,
        is_last_page: Optional[bool] = None,
        batch_index: int = 0,
        batch_count: int = 1,
        force_restart_upload: Optional[bool] = None,
        disable_stale_document_deletion_check: Optional[bool] = None,
    ) -> None:
        """Upload one pre-batched `/bulkindexdocuments` page."""
        document_list = list(documents)
        if self.observability:
            self.observability.log_batch_upload_started(
                batch_index=batch_index,
                batch_count=batch_count,
                batch_size=len(document_list),
                upload_id=upload_id,
                entity_type="document",
            )
            self.observability.record_upload_batch_size(len(document_list))
        start_time = time.time()
        try:
            with api_client() as client:
                self._call_api(
                    "documents.bulk_index",
                    lambda: client.indexing.documents.bulk_index(
                        datasource=self.datasource,
                        documents=document_list,
                        upload_id=upload_id,
                        is_first_page=is_first_page,
                        is_last_page=is_last_page,
                        force_restart_upload=force_restart_upload,
                        disable_stale_document_deletion_check=disable_stale_document_deletion_check,
                        **self._request_options(),
                    ),
                )
        except Exception as error:
            if self.observability:
                self.observability.log_batch_upload_failed(
                    batch_index=batch_index,
                    batch_count=batch_count,
                    error=error,
                    upload_id=upload_id,
                    entity_type="document",
                    batch_size=len(document_list),
                )
            raise
        else:
            if self.observability:
                self.observability.log_batch_upload_completed(
                    batch_index=batch_index,
                    batch_count=batch_count,
                    batch_size=len(document_list),
                    duration_ms=self._elapsed_ms(start_time),
                    upload_id=upload_id,
                    entity_type="document",
                )

    def delete_document(
        self,
        *,
        object_type: str,
        document_id: str,
        version: Optional[int] = None,
    ) -> None:
        """Delete a document using `/deletedocument`."""
        with api_client() as client:
            client.indexing.documents.delete(
                datasource=self.datasource,
                object_type=object_type,
                id=document_id,
                version=version,
                **self._request_options(),
            )

    def index_user(
        self,
        user: DatasourceUserDefinition,
        *,
        version: Optional[int] = None,
    ) -> None:
        """Add or update a datasource user using `/indexuser`."""
        with api_client() as client:
            client.indexing.permissions.index_user(
                datasource=self.datasource,
                user=user,
                version=version,
                **self._request_options(),
            )

    def bulk_index_users(
        self,
        users: Sequence[DatasourceUserDefinition],
        *,
        upload_id: Optional[str] = None,
        batch_size: int = 1000,
        force_restart_upload: Optional[bool] = None,
        disable_stale_data_deletion_check: Optional[bool] = None,
    ) -> None:
        """Replace datasource users using `/bulkindexusers`."""
        batches = self._batches(users, batch_size)
        if not batches:
            return

        upload_id = self._upload_id(upload_id)
        with api_client() as client:
            for i, batch in enumerate(batches):
                is_first_page = i == 0
                is_last_page = i == len(batches) - 1
                client.indexing.permissions.bulk_index_users(
                    datasource=self.datasource,
                    users=list(batch),
                    upload_id=upload_id,
                    is_first_page=is_first_page,
                    is_last_page=is_last_page,
                    force_restart_upload=self._first_page_value(
                        force_restart_upload, is_first_page
                    ),
                    disable_stale_data_deletion_check=self._last_page_value(
                        disable_stale_data_deletion_check, is_last_page
                    ),
                    **self._request_options(),
                )

    def index_group(
        self,
        group: DatasourceGroupDefinition,
        *,
        version: Optional[int] = None,
    ) -> None:
        """Add or update a datasource group using `/indexgroup`."""
        with api_client() as client:
            client.indexing.permissions.index_group(
                datasource=self.datasource,
                group=group,
                version=version,
                **self._request_options(),
            )

    def bulk_index_groups(
        self,
        groups: Sequence[DatasourceGroupDefinition],
        *,
        upload_id: Optional[str] = None,
        batch_size: int = 1000,
        force_restart_upload: Optional[bool] = None,
        disable_stale_data_deletion_check: Optional[bool] = None,
    ) -> None:
        """Replace datasource groups using `/bulkindexgroups`."""
        batches = self._batches(groups, batch_size)
        if not batches:
            return

        upload_id = self._upload_id(upload_id)
        with api_client() as client:
            for i, batch in enumerate(batches):
                is_first_page = i == 0
                is_last_page = i == len(batches) - 1
                client.indexing.permissions.bulk_index_groups(
                    datasource=self.datasource,
                    groups=list(batch),
                    upload_id=upload_id,
                    is_first_page=is_first_page,
                    is_last_page=is_last_page,
                    force_restart_upload=self._first_page_value(
                        force_restart_upload, is_first_page
                    ),
                    disable_stale_data_deletion_check=self._last_page_value(
                        disable_stale_data_deletion_check, is_last_page
                    ),
                    **self._request_options(),
                )

    def index_membership(
        self,
        membership: DatasourceMembershipDefinition,
        *,
        version: Optional[int] = None,
    ) -> None:
        """Add or update a datasource membership using `/indexmembership`."""
        with api_client() as client:
            client.indexing.permissions.index_membership(
                datasource=self.datasource,
                membership=membership,
                version=version,
                **self._request_options(),
            )

    def bulk_index_memberships(
        self,
        memberships: Sequence[DatasourceBulkMembershipDefinition],
        *,
        upload_id: Optional[str] = None,
        batch_size: int = 1000,
        force_restart_upload: Optional[bool] = None,
        group: Optional[str] = None,
    ) -> None:
        """Replace datasource memberships using `/bulkindexmemberships`."""
        batches = self._batches(memberships, batch_size)
        if not batches:
            return

        upload_id = self._upload_id(upload_id)
        with api_client() as client:
            for i, batch in enumerate(batches):
                is_first_page = i == 0
                is_last_page = i == len(batches) - 1
                client.indexing.permissions.bulk_index_memberships(
                    datasource=self.datasource,
                    memberships=list(batch),
                    upload_id=upload_id,
                    is_first_page=is_first_page,
                    is_last_page=is_last_page,
                    force_restart_upload=self._first_page_value(
                        force_restart_upload, is_first_page
                    ),
                    group=group,
                    **self._request_options(),
                )

    def delete_user(
        self,
        *,
        email: str,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource user using `/deleteuser`."""
        with api_client() as client:
            client.indexing.permissions.delete_user(
                datasource=self.datasource,
                email=email,
                version=version,
                **self._request_options(),
            )

    def delete_group(
        self,
        *,
        group_name: str,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource group using `/deletegroup`."""
        with api_client() as client:
            client.indexing.permissions.delete_group(
                datasource=self.datasource,
                group_name=group_name,
                version=version,
                **self._request_options(),
            )

    def delete_membership(
        self,
        membership: DatasourceMembershipDefinition,
        *,
        version: Optional[int] = None,
    ) -> None:
        """Delete a datasource membership using `/deletemembership`."""
        with api_client() as client:
            client.indexing.permissions.delete_membership(
                datasource=self.datasource,
                membership=membership,
                version=version,
                **self._request_options(),
            )

    def bulk_index_employees(
        self,
        employees: Sequence[EmployeeInfoDefinition],
        *,
        upload_id: Optional[str] = None,
        batch_size: int = 1000,
        force_restart_upload: Optional[bool] = None,
        disable_stale_data_deletion_check: Optional[bool] = None,
    ) -> None:
        """Replace employees using `/bulkindexemployees`."""
        batches = self._batches(employees, batch_size)
        if not batches:
            return

        upload_id = self._upload_id(upload_id)
        with api_client() as client:
            for i, batch in enumerate(batches):
                is_first_page = i == 0
                is_last_page = i == len(batches) - 1
                client.indexing.people.bulk_index(
                    employees=list(batch),
                    upload_id=upload_id,
                    is_first_page=is_first_page,
                    is_last_page=is_last_page,
                    force_restart_upload=self._first_page_value(
                        force_restart_upload, is_first_page
                    ),
                    disable_stale_data_deletion_check=self._last_page_value(
                        disable_stale_data_deletion_check, is_last_page
                    ),
                    **self._request_options(),
                )

    def _batches(self, items: Sequence[T], batch_size: int) -> list[Sequence[T]]:
        """Split items using the SDK's shared batching utility."""
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        return list(BatchProcessor(list(items), batch_size=batch_size))

    def _call_api(self, endpoint: str, call: Callable[[], Any]) -> Any:
        start_time = time.time()
        if self.observability:
            self.observability.record_api_request_count(endpoint)
        try:
            return call()
        except Exception as error:
            if self.observability:
                self.observability.record_api_request_error(endpoint, type(error).__name__)
            raise
        finally:
            if self.observability:
                self.observability.record_api_request_latency(self._elapsed_ms(start_time), endpoint)

    @staticmethod
    def _elapsed_ms(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    def _upload_id(self, upload_id: Optional[str]) -> str:
        return upload_id or str(uuid.uuid4())

    def _first_page_value(self, value: Optional[bool], is_first_page: bool) -> Optional[bool]:
        return True if value and is_first_page else None

    def _last_page_value(self, value: Optional[bool], is_last_page: bool) -> Optional[bool]:
        return True if value and is_last_page else None

    def _request_options(self) -> dict[str, Any]:
        """Return only generated-client request options explicitly configured."""
        options: dict[str, Any] = {}
        if self.retries is not None:
            options["retries"] = self.retries
        if self.server_url is not None:
            options["server_url"] = self.server_url
        if self.timeout_ms is not None:
            options["timeout_ms"] = self.timeout_ms
        if self.http_headers is not None:
            options["http_headers"] = self.http_headers
        return options
