"""Full-crawl Degreed catalog connector for the Glean Indexing SDK."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from datetime import datetime, timezone
from itertools import islice
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    CustomProperty,
    DocumentDefinition,
    DocumentPermissionsDefinition,
)

from glean.indexing.connectors import BaseStreamingDataClient, BaseStreamingDatasourceConnector
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.observability import ConnectorObservability
from glean.indexing.push import PushUploader
from glean.indexing.recipes.pull import (
    BasePullHttpStreamingDataClient,
    PullOptions,
    PullRetryOptions,
)

DEFAULT_API_BASE_URL = "https://api.degreed.com"
DEFAULT_DATASOURCE = "degreed"
DEFAULT_OAUTH_TOKEN_URL = "https://degreed.com/oauth/token"
DEFAULT_PAGE_SIZE = 1000

DegreedContentRecord = Mapping[str, Any]


class DegreedCrawlError(RuntimeError):
    """Raised when a Degreed crawl cannot safely complete."""


class DegreedContentDataClient(BasePullHttpStreamingDataClient[DegreedContentRecord]):
    """Fetch all organization-visible Degreed catalog content."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        api_base_url: str = DEFAULT_API_BASE_URL,
        oauth_token_url: str = DEFAULT_OAUTH_TOKEN_URL,
        organization_code: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        observability: ConnectorObservability | None = None,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("Degreed client ID and client secret must be non-empty")
        if not 1 <= page_size <= DEFAULT_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {DEFAULT_PAGE_SIZE}")

        normalized_api_url = api_base_url.rstrip("/")
        if not normalized_api_url.startswith(("https://", "http://")):
            raise ValueError("DEGREED_API_BASE_URL must be an absolute HTTP(S) URL")
        if not oauth_token_url.startswith(("https://", "http://")):
            raise ValueError("DEGREED_OAUTH_TOKEN_URL must be an absolute HTTP(S) URL")

        super().__init__(
            base_url=normalized_api_url,
            path="/api/v2/content",
            items_key="data",
            pagination="none",
            options=PullOptions(
                timeout_seconds=30,
                retries=PullRetryOptions(max_attempts=4),
                mask_params=True,
            ),
            observability=observability,
            client=client,
        )
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_token_url = oauth_token_url
        self.organization_code = organization_code
        self.page_size = page_size
        self._api_origin = _origin(normalized_api_url)
        self._clock = clock
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    def get_source_data(self, **kwargs: Any) -> Generator[DegreedContentRecord, None, None]:
        """Yield catalog records using Degreed's expiring next links."""
        if kwargs.get("since") is not None:
            raise ValueError("Incremental Degreed crawls are not supported")

        started = time.monotonic()
        item_count = 0
        success = False
        if self.observability:
            self.observability.log_data_fetch_started(path=self.path, pagination="links.next")

        try:
            current_path: str | None = self.path
            current_params: Mapping[str, Any] | None = {"limit": self.page_size}
            seen_next_links: set[str] = set()

            while current_path:
                response = self.http.get(
                    current_path,
                    params=current_params,
                    headers=self._request_headers(),
                )
                payload = response.json_dict()
                records = payload.get("data")
                if not isinstance(records, list) or not all(
                    isinstance(record, Mapping) for record in records
                ):
                    raise DegreedCrawlError("GET /api/v2/content returned invalid data")

                for record in cast(list[DegreedContentRecord], records):
                    item_count += 1
                    yield record

                next_link = _next_link(payload)
                if next_link is None:
                    success = True
                    return
                if next_link in seen_next_links:
                    raise DegreedCrawlError("Degreed pagination stopped advancing")
                self._validate_next_link(next_link)
                seen_next_links.add(next_link)
                current_path = next_link
                current_params = None
        finally:
            if success and self.observability:
                self.observability.log_data_fetch_completed(
                    item_count=item_count,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    path=self.path,
                    pagination="links.next",
                )

    def _request_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }
        if self.organization_code:
            headers["X-Degreed-Organization-Code"] = self.organization_code
        return headers

    def _get_access_token(self) -> str:
        now = self._clock()
        if self._access_token is not None and now < self._access_token_expires_at:
            return self._access_token

        response = self.http.post(
            self.oauth_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "content:read",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        payload = response.json_dict()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(access_token, str) or not access_token:
            raise DegreedCrawlError("Degreed token response did not include an access token")
        if (
            not isinstance(expires_in, (int, float))
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise DegreedCrawlError("Degreed token response included an invalid expires_in")

        expires_in_seconds = float(expires_in)
        refresh_margin = min(60.0, expires_in_seconds / 10)
        self._access_token = access_token
        self._access_token_expires_at = now + expires_in_seconds - refresh_margin
        return access_token

    def _validate_next_link(self, next_link: str) -> None:
        parsed = urlparse(next_link)
        if parsed.scheme or parsed.netloc:
            if _origin(next_link) != self._api_origin:
                raise DegreedCrawlError(
                    "Degreed returned a pagination link outside the configured API origin"
                )


class DegreedConnector(BaseStreamingDatasourceConnector[DegreedContentRecord]):
    """Transform Degreed catalog records and push a full replacement to Glean."""

    configuration = CustomDatasourceConfig(
        name=DEFAULT_DATASOURCE,
        display_name="Degreed",
        url_regex=r"https://(?:[^/]+\.)?degreed\.(?:com|app)/.*",
        trust_url_regex_for_view_activity=True,
    )

    def __init__(
        self,
        data_client: BaseStreamingDataClient[DegreedContentRecord],
        *,
        observability: ConnectorObservability | None = None,
    ) -> None:
        super().__init__(DEFAULT_DATASOURCE, data_client)
        if observability is not None:
            self._observability = observability

    @classmethod
    def from_env(cls) -> DegreedConnector:
        """Create a production connector from environment variables."""
        observability = ConnectorObservability(
            DEFAULT_DATASOURCE, crawl_mode=IndexingMode.FULL.value
        )
        data_client = DegreedContentDataClient(
            _required_env("DEGREED_CLIENT_ID"),
            _required_env("DEGREED_CLIENT_SECRET"),
            api_base_url=os.getenv("DEGREED_API_BASE_URL", DEFAULT_API_BASE_URL),
            oauth_token_url=os.getenv("DEGREED_OAUTH_TOKEN_URL", DEFAULT_OAUTH_TOKEN_URL),
            organization_code=os.getenv("DEGREED_ORGANIZATION_CODE"),
            observability=observability,
        )
        return cls(data_client, observability=observability)

    def transform(self, data: Sequence[DegreedContentRecord]) -> Sequence[DocumentDefinition]:
        """Map Degreed content records to Glean documents."""
        started = time.monotonic()
        self.observability.log_transform_started(len(data))
        documents: list[DocumentDefinition] = []
        skipped_count = 0

        for record in data:
            document = self._to_document(record)
            if document is None:
                skipped_count += 1
                continue
            documents.append(document)

        self.observability.log_transform_completed(
            input_count=len(data),
            output_count=len(documents),
            duration_ms=int((time.monotonic() - started) * 1000),
            skipped_count=skipped_count,
        )
        self.observability.increment_counter("documents_skipped", skipped_count)
        return documents

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: ConnectorOptions | None = None,
    ) -> None:
        """Run an authoritative streaming replacement of Degreed documents."""
        if mode != IndexingMode.FULL:
            raise ValueError("Incremental Degreed crawls are not supported")

        self.observability.start_execution()
        try:
            uploader = PushUploader(
                datasource=self.name,
                timeout_ms=options.upload_timeout_ms if options else None,
                observability=self.observability,
            )
            self._upload_documents(uploader, options)
            self.observability.record_crawl_success()
        except Exception as error:
            self.observability.increment_counter("indexing_errors")
            self.observability.record_crawl_failure(type(error).__name__)
            self.observability.fail_execution(error)
            raise
        finally:
            self.observability.end_execution()

    def _upload_documents(self, uploader: PushUploader, options: ConnectorOptions | None) -> None:
        upload_id = self.generate_upload_id()
        iterator = iter(self.get_data())
        batch = list(islice(iterator, self.batch_size))
        is_first_page = True
        batch_index = 0

        if not batch:
            uploader.bulk_index_single_batch_upload(
                documents=[],
                upload_id=upload_id,
                is_first_page=True,
                is_last_page=True,
                force_restart_upload=True if options and options.force_restart else None,
                disable_stale_document_deletion_check=True
                if options and options.disable_stale_deletion_check
                else None,
            )
            return

        while batch:
            sentinel = object()
            next_item = next(iterator, sentinel)
            is_last_page = next_item is sentinel
            documents = self.transform(batch)
            uploader.bulk_index_single_batch_upload(
                documents=documents,
                upload_id=upload_id,
                is_first_page=is_first_page,
                is_last_page=is_last_page,
                batch_index=batch_index,
                force_restart_upload=True
                if options and options.force_restart and is_first_page
                else None,
                disable_stale_document_deletion_check=True
                if options and options.disable_stale_deletion_check and is_last_page
                else None,
            )
            self.observability.increment_counter("documents_indexed", len(documents))
            if is_last_page:
                return
            batch = [cast(DegreedContentRecord, next_item), *islice(iterator, self.batch_size - 1)]
            is_first_page = False
            batch_index += 1

    def _to_document(self, record: DegreedContentRecord) -> DocumentDefinition | None:
        record_id = _non_empty_string(record.get("id"))
        attributes = record.get("attributes")
        if record_id is None or not isinstance(attributes, Mapping):
            return None

        title = _non_empty_string(attributes.get("title"))
        view_url = _non_empty_string(attributes.get("degreed-url")) or _non_empty_string(
            attributes.get("url")
        )
        if title is None or view_url is None:
            return None

        content_type = _non_empty_string(attributes.get("content-type"))
        provider = _non_empty_string(attributes.get("provider"))
        language = _non_empty_string(attributes.get("language"))
        summary = _non_empty_string(attributes.get("summary"))
        skills = _skills(record.get("relationships"))
        tags = _unique_strings([content_type, provider, language, *skills])

        return DocumentDefinition(
            datasource=self.name,
            id=record_id,
            object_type="learning_content",
            title=title,
            view_url=view_url,
            summary=ContentDefinition(mime_type="text/plain", text_content=summary)
            if summary
            else None,
            body=ContentDefinition(
                mime_type="text/plain",
                text_content=_document_text(attributes, skills),
            ),
            permissions=DocumentPermissionsDefinition(allow_all_datasource_users_access=True),
            created_at=_timestamp(attributes.get("created-at")),
            updated_at=_timestamp(attributes.get("modified-at"))
            or _timestamp(attributes.get("created-at")),
            tags=tags,
            custom_properties=_custom_properties(attributes, skills),
        )


def _next_link(payload: Mapping[str, Any]) -> str | None:
    links = payload.get("links")
    if links is None:
        return None
    if not isinstance(links, Mapping):
        raise DegreedCrawlError("GET /api/v2/content returned invalid links")
    next_link = links.get("next")
    if next_link in (None, ""):
        return None
    if not isinstance(next_link, str):
        raise DegreedCrawlError("GET /api/v2/content returned an invalid next link")
    return next_link


def _document_text(attributes: Mapping[str, Any], skills: Sequence[str]) -> str:
    lines: list[str] = []
    summary = _non_empty_string(attributes.get("summary"))
    if summary:
        lines.append(summary)

    metadata = [
        ("Content type", _non_empty_string(attributes.get("content-type"))),
        ("Provider", _non_empty_string(attributes.get("provider"))),
        ("Format", _non_empty_string(attributes.get("format"))),
        ("Language", _non_empty_string(attributes.get("language"))),
        ("Learning minutes", _number_string(attributes.get("learning-minutes"))),
        ("Skills", ", ".join(skills) if skills else None),
    ]
    lines.extend(f"{label}: {value}" for label, value in metadata if value)
    return "\n".join(lines)


def _custom_properties(
    attributes: Mapping[str, Any], skills: Sequence[str]
) -> list[CustomProperty]:
    values = [
        ("content_type", attributes.get("content-type")),
        ("external_id", attributes.get("external-id")),
        ("provider", attributes.get("provider")),
        ("language", attributes.get("language")),
        ("learning_minutes", attributes.get("learning-minutes")),
        ("is_internal", attributes.get("is-internal")),
        ("publish_date", attributes.get("publish-date")),
        ("source_url", attributes.get("url")),
        ("skills", list(skills) or None),
    ]
    return [
        CustomProperty(name=name, value=value)
        for name, value in values
        if value is not None and value != ""
    ]


def _skills(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    skills: list[str] = []
    for relationship in value:
        if not isinstance(relationship, Mapping):
            continue
        skill_relationship = relationship.get("Skill")
        if not isinstance(skill_relationship, Mapping):
            continue
        skill_data = skill_relationship.get("data")
        if not isinstance(skill_data, list):
            continue
        for skill in skill_data:
            if isinstance(skill, Mapping):
                skill_id = _non_empty_string(skill.get("id"))
                if skill_id:
                    skills.append(skill_id)
    return _unique_strings(skills)


def _timestamp(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _number_string(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _non_empty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unique_strings(values: Sequence[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _origin(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.netloc.lower()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} must be set")
    return value
