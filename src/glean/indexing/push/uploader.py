"""Upload orchestration for the Glean push layer."""

import logging
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional, TypeVar

from glean.api_client.models import DocumentDefinition, EmployeeInfoDefinition
from glean.indexing.common import BatchProcessor, api_client
from glean.indexing.push.api import GleanPushApi
from glean.indexing.push.batching import iter_sized_batches, json_size_bytes
from glean.indexing.push.options import PushOptions
from glean.indexing.push.results import BatchUploadResult, UploadResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PushUploader:
    """Coordinates SDK-owned push operations against the generated Glean client."""

    def __init__(self, client_factory: Callable[[], Any] = api_client):
        """Initialize the uploader with a client context-manager factory."""
        self._client_factory = client_factory

    def index_documents(
        self,
        *,
        datasource: str,
        documents: Sequence[DocumentDefinition],
        batch_size: int,
        options: PushOptions,
        upload_id: Optional[str] = None,
    ) -> UploadResult:
        """Upsert documents through non-session `indexdocuments` calls."""
        batches = self._document_batches(documents, batch_size=batch_size, options=options)

        def upload(api: GleanPushApi, batch: Sequence[DocumentDefinition], _index: int) -> None:
            api.index_documents(
                datasource=datasource, documents=batch, upload_id=upload_id, options=options
            )

        return self._upload_sequential(
            operation="indexdocuments", batches=batches, upload_id=upload_id, upload=upload
        )

    def upload_documents(
        self,
        *,
        datasource: str,
        documents: Sequence[DocumentDefinition],
        batch_size: int,
        options: PushOptions,
        upload_id: Optional[str] = None,
    ) -> UploadResult:
        """Upload documents through `bulkindexdocuments` with concurrent middle batches."""
        if not documents:
            return UploadResult(
                operation="bulkindexdocuments", item_count=0, batch_count=0, upload_id=upload_id
            )

        upload_id = upload_id or str(uuid.uuid4())
        batches = self._document_batches(documents, batch_size=batch_size, options=options)
        total_batches = len(batches)

        if total_batches == 1:
            self._upload_document_batch(
                datasource=datasource,
                batch=batches[0],
                batch_index=0,
                total_batches=1,
                upload_id=upload_id,
                options=options,
            )
            return self._success_result("bulkindexdocuments", documents, batches, upload_id)

        self._upload_document_batch(
            datasource=datasource,
            batch=batches[0],
            batch_index=0,
            total_batches=total_batches,
            upload_id=upload_id,
            options=options,
        )

        middle_results: list[BatchUploadResult] = []
        middle_batches = list(enumerate(batches[1:-1], start=1))
        if middle_batches:
            max_workers = max(1, options.upload_concurrency)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._upload_document_batch,
                        datasource=datasource,
                        batch=batch,
                        batch_index=batch_index,
                        total_batches=total_batches,
                        upload_id=upload_id,
                        options=options,
                    ): batch_index
                    for batch_index, batch in middle_batches
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                        batch_index = futures[future]
                        middle_results.append(
                            BatchUploadResult(
                                operation="bulkindexdocuments",
                                item_count=len(batches[batch_index]),
                                batch_index=batch_index,
                            )
                        )
                    except Exception as exc:
                        batch_index = futures[future]
                        middle_results.append(
                            BatchUploadResult(
                                operation="bulkindexdocuments",
                                item_count=len(batches[batch_index]),
                                batch_index=batch_index,
                                success=False,
                                error=str(exc),
                            )
                        )
                        raise

        self._upload_document_batch(
            datasource=datasource,
            batch=batches[-1],
            batch_index=total_batches - 1,
            total_batches=total_batches,
            upload_id=upload_id,
            options=options,
        )

        batch_results = [
            BatchUploadResult(
                operation="bulkindexdocuments", item_count=len(batches[0]), batch_index=0
            ),
            *sorted(middle_results, key=lambda result: result.batch_index),
            BatchUploadResult(
                operation="bulkindexdocuments",
                item_count=len(batches[-1]),
                batch_index=total_batches - 1,
            ),
        ]
        return UploadResult(
            operation="bulkindexdocuments",
            item_count=len(documents),
            batch_count=total_batches,
            upload_id=upload_id,
            batches=tuple(batch_results),
        )

    def upload_document_batch(
        self,
        *,
        datasource: str,
        documents: Sequence[DocumentDefinition],
        upload_id: str,
        is_first_page: bool,
        is_last_page: bool,
        options: PushOptions,
    ) -> UploadResult:
        """Upload a pre-planned `bulkindexdocuments` page.

        Streaming connectors discover first/last-page state as they iterate, so
        they feed already-sized batches into this method instead of asking the
        push layer to pre-plan the full upload.
        """
        with self._client_factory() as client:
            GleanPushApi(client).bulk_index_documents(
                datasource=datasource,
                documents=documents,
                upload_id=upload_id,
                is_first_page=is_first_page,
                is_last_page=is_last_page,
                options=options,
            )
        return UploadResult(
            operation="bulkindexdocuments",
            item_count=len(documents),
            batch_count=1,
            upload_id=upload_id,
            batches=(
                BatchUploadResult(
                    operation="bulkindexdocuments",
                    item_count=len(documents),
                    batch_index=0,
                ),
            ),
        )

    def upload_users(
        self, *, datasource: str, users: Sequence[Any], batch_size: int, options: PushOptions
    ) -> UploadResult:
        """Upload datasource users through the bulk user endpoint."""
        upload_id = str(uuid.uuid4())

        def upload(api: GleanPushApi, batch: Sequence[Any], index: int, total: int) -> None:
            api.bulk_index_users(
                datasource=datasource,
                users=batch,
                upload_id=upload_id,
                is_first_page=index == 0,
                is_last_page=index == total - 1,
                options=options,
            )

        return self._upload_session_sequential(
            "bulkindexusers", users, batch_size, upload_id, upload
        )

    def upload_groups(
        self, *, datasource: str, groups: Sequence[Any], batch_size: int, options: PushOptions
    ) -> UploadResult:
        """Upload datasource groups through the bulk group endpoint."""
        upload_id = str(uuid.uuid4())

        def upload(api: GleanPushApi, batch: Sequence[Any], index: int, total: int) -> None:
            api.bulk_index_groups(
                datasource=datasource,
                groups=batch,
                upload_id=upload_id,
                is_first_page=index == 0,
                is_last_page=index == total - 1,
                options=options,
            )

        return self._upload_session_sequential(
            "bulkindexgroups", groups, batch_size, upload_id, upload
        )

    def upload_memberships(
        self,
        *,
        datasource: str,
        memberships: Sequence[Any],
        batch_size: int,
        options: PushOptions,
        group: Optional[str] = None,
    ) -> UploadResult:
        """Upload datasource memberships through the bulk membership endpoint."""
        upload_id = str(uuid.uuid4())

        def upload(api: GleanPushApi, batch: Sequence[Any], index: int, total: int) -> None:
            api.bulk_index_memberships(
                datasource=datasource,
                memberships=batch,
                upload_id=upload_id,
                is_first_page=index == 0,
                is_last_page=index == total - 1,
                options=options,
                group=group,
            )

        return self._upload_session_sequential(
            "bulkindexmemberships", memberships, batch_size, upload_id, upload
        )

    def upload_employees(
        self,
        *,
        employees: Sequence[EmployeeInfoDefinition],
        batch_size: int,
        options: PushOptions,
    ) -> UploadResult:
        """Upload employees through the bulk people endpoint."""
        upload_id = str(uuid.uuid4())

        def upload(
            api: GleanPushApi, batch: Sequence[EmployeeInfoDefinition], index: int, total: int
        ) -> None:
            api.bulk_index_employees(
                employees=batch,
                upload_id=upload_id,
                is_first_page=index == 0,
                is_last_page=index == total - 1,
                options=options,
            )

        return self._upload_session_sequential(
            "bulkindexemployees", employees, batch_size, upload_id, upload
        )

    def index_users(
        self, *, datasource: str, users: Sequence[Any], options: PushOptions
    ) -> UploadResult:
        """Index datasource users through incremental `indexuser` calls."""

        def upload(api: GleanPushApi, user: Any, _index: int) -> None:
            api.index_user(datasource=datasource, user=user, options=options)

        return self._upload_items("indexuser", users, upload)

    def index_groups(
        self, *, datasource: str, groups: Sequence[Any], options: PushOptions
    ) -> UploadResult:
        """Index datasource groups through incremental `indexgroup` calls."""

        def upload(api: GleanPushApi, group: Any, _index: int) -> None:
            api.index_group(datasource=datasource, group=group, options=options)

        return self._upload_items("indexgroup", groups, upload)

    def index_memberships(
        self, *, datasource: str, memberships: Sequence[Any], options: PushOptions
    ) -> UploadResult:
        """Index datasource memberships through incremental `indexmembership` calls."""

        def upload(api: GleanPushApi, membership: Any, _index: int) -> None:
            api.index_membership(datasource=datasource, membership=membership, options=options)

        return self._upload_items("indexmembership", memberships, upload)

    def index_employees(
        self, *, employees: Sequence[EmployeeInfoDefinition], options: PushOptions
    ) -> UploadResult:
        """Index employees through incremental people `index` calls."""

        def upload(api: GleanPushApi, employee: EmployeeInfoDefinition, _index: int) -> None:
            api.index_employee(employee=employee, options=options)

        return self._upload_items("indexemployee", employees, upload)

    def delete_document(
        self,
        *,
        datasource: str,
        object_type: str,
        id: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> UploadResult:
        """Delete a single document."""
        with self._client_factory() as client:
            GleanPushApi(client).delete_document(
                datasource=datasource,
                object_type=object_type,
                id=id,
                version=version,
                options=options,
            )
        return UploadResult(operation="deletedocument", item_count=1, batch_count=1)

    def delete_user(
        self,
        *,
        datasource: str,
        email: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> UploadResult:
        """Delete a single datasource user."""
        with self._client_factory() as client:
            GleanPushApi(client).delete_user(
                datasource=datasource,
                email=email,
                version=version,
                options=options,
            )
        return UploadResult(operation="deleteuser", item_count=1, batch_count=1)

    def delete_group(
        self,
        *,
        datasource: str,
        group_name: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> UploadResult:
        """Delete a single datasource group."""
        with self._client_factory() as client:
            GleanPushApi(client).delete_group(
                datasource=datasource,
                group_name=group_name,
                version=version,
                options=options,
            )
        return UploadResult(operation="deletegroup", item_count=1, batch_count=1)

    def delete_membership(
        self,
        *,
        datasource: str,
        membership: Any,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> UploadResult:
        """Delete a single datasource membership."""
        with self._client_factory() as client:
            GleanPushApi(client).delete_membership(
                datasource=datasource,
                membership=membership,
                version=version,
                options=options,
            )
        return UploadResult(operation="deletemembership", item_count=1, batch_count=1)

    def delete_employee(
        self,
        *,
        employee_email: str,
        options: PushOptions,
        version: Optional[int] = None,
    ) -> UploadResult:
        """Delete a single employee."""
        with self._client_factory() as client:
            GleanPushApi(client).delete_employee(
                employee_email=employee_email,
                version=version,
                options=options,
            )
        return UploadResult(operation="deleteemployee", item_count=1, batch_count=1)

    def update_permissions(
        self,
        *,
        datasource: str,
        permissions: Any,
        options: PushOptions,
        object_type: Optional[str] = None,
        id: Optional[str] = None,
        view_url: Optional[str] = None,
    ) -> UploadResult:
        """Update permissions for a single document."""
        with self._client_factory() as client:
            GleanPushApi(client).update_permissions(
                datasource=datasource,
                permissions=permissions,
                object_type=object_type,
                id=id,
                view_url=view_url,
                options=options,
            )
        return UploadResult(operation="updatepermissions", item_count=1, batch_count=1)

    def _upload_document_batch(
        self,
        *,
        datasource: str,
        batch: Sequence[DocumentDefinition],
        batch_index: int,
        total_batches: int,
        upload_id: str,
        options: PushOptions,
    ) -> None:
        logger.info(
            "Uploading document batch %s/%s (%s documents)",
            batch_index + 1,
            total_batches,
            len(batch),
        )
        with self._client_factory() as client:
            GleanPushApi(client).bulk_index_documents(
                datasource=datasource,
                documents=batch,
                upload_id=upload_id,
                is_first_page=batch_index == 0,
                is_last_page=batch_index == total_batches - 1,
                options=options,
            )

    def _document_batches(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        batch_size: int,
        options: PushOptions,
    ) -> list[list[DocumentDefinition]]:
        return list(
            iter_sized_batches(
                documents,
                max_items=batch_size,
                max_bytes=options.document_batch_max_bytes,
                size_fn=json_size_bytes,
            )
        )

    def _upload_session_sequential(
        self,
        operation: str,
        items: Sequence[T],
        batch_size: int,
        upload_id: str,
        upload: Callable[[GleanPushApi, Sequence[T], int, int], None],
    ) -> UploadResult:
        batches = [list(batch) for batch in BatchProcessor(list(items), batch_size=batch_size)]

        def upload_batch(api: GleanPushApi, batch: Sequence[T], index: int) -> None:
            upload(api, batch, index, len(batches))

        return self._upload_sequential(
            operation=operation, batches=batches, upload_id=upload_id, upload=upload_batch
        )

    def _upload_sequential(
        self,
        *,
        operation: str,
        batches: Sequence[Sequence[T]],
        upload_id: Optional[str],
        upload: Callable[[GleanPushApi, Sequence[T], int], None],
    ) -> UploadResult:
        batch_results: list[BatchUploadResult] = []
        item_count = sum(len(batch) for batch in batches)

        for index, batch in enumerate(batches):
            try:
                with self._client_factory() as client:
                    upload(GleanPushApi(client), batch, index)
                batch_results.append(
                    BatchUploadResult(operation=operation, item_count=len(batch), batch_index=index)
                )
            except Exception as exc:
                batch_results.append(
                    BatchUploadResult(
                        operation=operation,
                        item_count=len(batch),
                        batch_index=index,
                        success=False,
                        error=str(exc),
                    )
                )
                raise

        return UploadResult(
            operation=operation,
            item_count=item_count,
            batch_count=len(batches),
            upload_id=upload_id,
            batches=tuple(batch_results),
        )

    def _upload_items(
        self,
        operation: str,
        items: Sequence[T],
        upload: Callable[[GleanPushApi, T, int], None],
    ) -> UploadResult:
        batch_results: list[BatchUploadResult] = []
        for index, item in enumerate(items):
            try:
                with self._client_factory() as client:
                    upload(GleanPushApi(client), item, index)
                batch_results.append(
                    BatchUploadResult(operation=operation, item_count=1, batch_index=index)
                )
            except Exception as exc:
                batch_results.append(
                    BatchUploadResult(
                        operation=operation,
                        item_count=1,
                        batch_index=index,
                        success=False,
                        error=str(exc),
                    )
                )
                raise

        return UploadResult(
            operation=operation,
            item_count=len(items),
            batch_count=len(items),
            batches=tuple(batch_results),
        )

    def _success_result(
        self,
        operation: str,
        items: Sequence[Any],
        batches: Sequence[Sequence[Any]],
        upload_id: Optional[str],
    ) -> UploadResult:
        return UploadResult(
            operation=operation,
            item_count=len(items),
            batch_count=len(batches),
            upload_id=upload_id,
            batches=tuple(
                BatchUploadResult(operation=operation, item_count=len(batch), batch_index=index)
                for index, batch in enumerate(batches)
            ),
        )
