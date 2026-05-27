"""First-class wrappers for push indexing APIs."""

from typing import Any, Mapping, Optional, Sequence

from glean.api_client.models import (
    DatasourceGroupDefinition,
    DatasourceMembershipDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
)

from glean.indexing.common import api_client


class PushUploader:
    """Thin uploader for push indexing APIs.

    Existing connector bulk flows intentionally do not use this class yet.
    """

    def __init__(
        self,
        datasource: str,
        *,
        retries: Optional[Any] = None,
        server_url: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        http_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        """Initialize an uploader for a datasource.

        Args:
            datasource: Datasource name to send with each indexing API call.
            retries: Optional generated-client retry configuration.
            server_url: Optional per-call server URL override.
            timeout_ms: Optional per-call timeout override in milliseconds.
            http_headers: Optional per-call HTTP headers.
        """
        self.datasource = datasource
        self.retries = retries
        self.server_url = server_url
        self.timeout_ms = timeout_ms
        self.http_headers = http_headers

    def index_documents(
        self,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: Optional[str] = None,
    ) -> None:
        """Add or update multiple documents using `/indexdocuments`."""
        with api_client() as client:
            client.indexing.documents.index(
                datasource=self.datasource,
                documents=list(documents),
                upload_id=upload_id,
                **self._request_options(),
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
