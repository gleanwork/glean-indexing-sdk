"""Full-crawl Zulip connector for the Glean Indexing SDK."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Any, cast

import httpx
from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    CustomDatasourceConfigConnectorType,
    DatasourceBulkMembershipDefinition,
    DatasourceCategory,
    DatasourceGroupDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    UserReferenceDefinition,
)

from glean.indexing.connectors import BaseStreamingDataClient, BaseStreamingDatasourceConnector
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.observability import ConnectorObservability
from glean.indexing.push import PushUploader
from glean.indexing.recipes.pull import PullHttpClient, PullOptions, PullRetryOptions

DEFAULT_DATASOURCE = "zulip"
DEFAULT_PAGE_SIZE = 1000


class ZulipCrawlError(RuntimeError):
    """Raised when a Zulip crawl cannot safely complete."""


@dataclass(frozen=True)
class ZulipStream:
    """Channel metadata needed by the content and permission crawls."""

    stream_id: int
    name: str
    invite_only: bool
    is_web_public: bool


@dataclass(frozen=True)
class ZulipUser:
    """Zulip user fields needed for Glean identity mapping."""

    user_id: int
    email: str
    delivery_email: str | None
    full_name: str
    is_active: bool
    is_bot: bool


@dataclass(frozen=True)
class ZulipMessageRecord:
    """One channel message enriched with its channel metadata."""

    message: Mapping[str, Any]
    stream: ZulipStream


@dataclass(frozen=True)
class ZulipCrawlContext:
    """Identity and permission data shared with document transformation."""

    streams: Mapping[int, ZulipStream]
    users: Mapping[int, ZulipUser]
    private_members: Mapping[int, tuple[int, ...]]


def create_zulip_http_client(
    site: str,
    email: str,
    api_key: str,
    *,
    observability: ConnectorObservability | None = None,
    client: httpx.Client | None = None,
) -> PullHttpClient:
    """Create the shared, retrying Zulip API client."""
    normalized_site = site.rstrip("/")
    if not normalized_site.startswith(("https://", "http://")):
        raise ValueError("ZULIP_SITE must be an absolute HTTP(S) URL")
    if not email or not api_key:
        raise ValueError("ZULIP_EMAIL and ZULIP_API_KEY must be non-empty")

    encoded_credentials = base64.b64encode(f"{email}:{api_key}".encode()).decode()
    return PullHttpClient(
        base_url=f"{normalized_site}/api/v1/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
        },
        options=PullOptions(
            timeout_seconds=30,
            retries=PullRetryOptions(max_attempts=4),
            mask_params=True,
        ),
        observability=observability,
        client=client,
    )


class ZulipIdentityClient:
    """Fetch Zulip channels, users, and private-channel memberships."""

    def __init__(self, http_client: PullHttpClient) -> None:
        self.http_client = http_client

    def fetch_context(self) -> ZulipCrawlContext:
        """Fetch and validate all identity information needed by a full crawl."""
        streams = self._get_streams()
        users = self._get_users()
        private_members = {
            stream.stream_id: self._get_private_members(stream, users)
            for stream in streams.values()
            if stream.invite_only
        }
        return ZulipCrawlContext(streams=streams, users=users, private_members=private_members)

    def _get_streams(self) -> dict[int, ZulipStream]:
        payload = _response_object(
            self.http_client.get(
                "streams",
                params={
                    "include_can_access_content": "true",
                    "exclude_archived": "true",
                },
            ),
            "GET /streams",
        )
        raw_streams = _object_list(payload, "streams", "GET /streams")
        streams: dict[int, ZulipStream] = {}
        for raw_stream in raw_streams:
            if bool(raw_stream.get("is_archived", False)):
                continue
            stream_id = _required_int(raw_stream, "stream_id", "GET /streams")
            streams[stream_id] = ZulipStream(
                stream_id=stream_id,
                name=_required_str(raw_stream, "name", "GET /streams"),
                invite_only=bool(raw_stream.get("invite_only", False)),
                is_web_public=bool(raw_stream.get("is_web_public", False)),
            )
        return streams

    def _get_users(self) -> dict[int, ZulipUser]:
        payload = _response_object(self.http_client.get("users"), "GET /users")
        raw_users = _object_list(payload, "members", "GET /users")
        users: dict[int, ZulipUser] = {}
        for raw_user in raw_users:
            user_id = _required_int(raw_user, "user_id", "GET /users")
            delivery_email = raw_user.get("delivery_email")
            users[user_id] = ZulipUser(
                user_id=user_id,
                email=_required_str(raw_user, "email", "GET /users"),
                delivery_email=delivery_email
                if isinstance(delivery_email, str) and delivery_email
                else None,
                full_name=_required_str(raw_user, "full_name", "GET /users"),
                is_active=bool(raw_user.get("is_active", False)),
                is_bot=bool(raw_user.get("is_bot", False)),
            )
        return users

    def _get_private_members(
        self, stream: ZulipStream, users: Mapping[int, ZulipUser]
    ) -> tuple[int, ...]:
        payload = _response_object(
            self.http_client.get(f"streams/{stream.stream_id}/members"),
            f"GET /streams/{stream.stream_id}/members",
        )
        raw_members = payload.get("subscribers")
        if not isinstance(raw_members, list) or not all(
            isinstance(member, int) and not isinstance(member, bool) for member in raw_members
        ):
            raise ZulipCrawlError(
                f"GET /streams/{stream.stream_id}/members returned invalid subscribers"
            )

        human_members: list[int] = []
        for member_id in raw_members:
            user = users.get(member_id)
            if user is None:
                raise ZulipCrawlError(
                    f"Private channel {stream.stream_id} references unknown user {member_id}"
                )
            if user.is_bot or not user.is_active:
                continue
            if user.delivery_email is None:
                raise ZulipCrawlError(
                    f"Private channel {stream.stream_id} member {member_id} has no visible delivery_email; refusing to index private content"
                )
            human_members.append(member_id)

        if not human_members:
            raise ZulipCrawlError(
                f"Private channel {stream.stream_id} has no resolvable active human members"
            )
        return tuple(human_members)


class ZulipMessageDataClient(BaseStreamingDataClient[ZulipMessageRecord]):
    """Stream every accessible channel using Zulip's ID-anchor pagination."""

    def __init__(self, http_client: PullHttpClient, *, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        if not 1 <= page_size <= DEFAULT_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {DEFAULT_PAGE_SIZE}")
        self.http_client = http_client
        self.page_size = page_size
        self._streams: tuple[ZulipStream, ...] | None = None

    def set_streams(self, streams: Sequence[ZulipStream]) -> None:
        """Set the validated channels to crawl after identity bootstrap."""
        self._streams = tuple(streams)

    def get_source_data(self, **kwargs: Any) -> Generator[ZulipMessageRecord, None, None]:
        """Yield channel messages oldest-to-newest."""
        if kwargs.get("since") is not None:
            raise ValueError("Incremental Zulip crawls are not supported")
        if self._streams is None:
            raise ZulipCrawlError("Identity bootstrap must complete before fetching messages")

        for stream in self._streams:
            yield from self._get_stream_messages(stream)

    def _get_stream_messages(
        self, stream: ZulipStream
    ) -> Generator[ZulipMessageRecord, None, None]:
        anchor: str | int = "oldest"
        include_anchor = True
        while True:
            payload = _response_object(
                self.http_client.get(
                    "messages",
                    params={
                        "anchor": anchor,
                        "include_anchor": json.dumps(include_anchor),
                        "num_before": 0,
                        "num_after": self.page_size,
                        "narrow": json.dumps([{"operator": "channel", "operand": stream.name}]),
                        "apply_markdown": "true",
                        "allow_empty_topic_name": "true",
                    },
                ),
                "GET /messages",
            )
            if payload.get("history_limited") is True:
                raise ZulipCrawlError(
                    f"Zulip reported limited history for channel {stream.stream_id}"
                )

            messages = _object_list(payload, "messages", "GET /messages")
            for message in messages:
                if _required_int(message, "stream_id", "GET /messages") != stream.stream_id:
                    raise ZulipCrawlError(
                        f"GET /messages returned a message outside channel {stream.stream_id}"
                    )
                yield ZulipMessageRecord(message=message, stream=stream)

            if payload.get("found_newest") is True:
                return
            if not messages:
                raise ZulipCrawlError(
                    f"Message pagination stopped advancing for channel {stream.stream_id}"
                )

            next_anchor = max(_required_int(message, "id", "GET /messages") for message in messages)
            if isinstance(anchor, int) and next_anchor <= anchor:
                raise ZulipCrawlError(
                    f"Message pagination stopped advancing for channel {stream.stream_id}"
                )
            anchor = next_anchor
            include_anchor = False


class ZulipConnector(BaseStreamingDatasourceConnector[ZulipMessageRecord]):
    """Push Zulip channel messages and their ACLs to Glean."""

    configuration = CustomDatasourceConfig(
        name=DEFAULT_DATASOURCE,
        display_name="Zulip",
        datasource_category=DatasourceCategory.MESSAGING,
        connector_type=CustomDatasourceConfigConnectorType.PUSH_API,
        url_regex=r"https?://[^/]+/#narrow/channel/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=False,
    )

    def __init__(
        self,
        site: str,
        message_client: ZulipMessageDataClient,
        identity_client: ZulipIdentityClient,
        *,
        name: str = DEFAULT_DATASOURCE,
    ) -> None:
        if name != self.configuration.name:
            raise ValueError(
                f"Connector name must match configured datasource {self.configuration.name!r}"
            )
        super().__init__(name, message_client)
        self.site = site.rstrip("/")
        self.message_client = message_client
        self.identity_client = identity_client
        self._context: ZulipCrawlContext | None = None

    @classmethod
    def from_env(cls) -> ZulipConnector:
        """Build a production connector from environment variables."""
        site = os.environ["ZULIP_SITE"]
        observability = ConnectorObservability(DEFAULT_DATASOURCE, crawl_mode="full")
        http_client = create_zulip_http_client(
            site,
            os.environ["ZULIP_EMAIL"],
            os.environ["ZULIP_API_KEY"],
            observability=observability,
        )
        connector = cls(site, ZulipMessageDataClient(http_client), ZulipIdentityClient(http_client))
        connector._observability = observability
        return connector

    def transform(self, data: Sequence[ZulipMessageRecord]) -> Sequence[DocumentDefinition]:
        """Map Zulip messages to Glean documents."""
        if self._context is None:
            raise ZulipCrawlError("Identity bootstrap must complete before transforming messages")

        started = time.monotonic()
        self.observability.log_transform_started(len(data))
        documents = [self._to_document(record) for record in data]
        self.observability.log_transform_completed(
            input_count=len(data),
            output_count=len(documents),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return documents

    def index_data(
        self, mode: IndexingMode = IndexingMode.FULL, options: ConnectorOptions | None = None
    ) -> None:
        """Run identity replacement followed by streaming document replacement."""
        if mode != IndexingMode.FULL:
            raise ValueError("Incremental Zulip crawls are not supported")

        self.observability.start_execution()
        try:
            self.observability.log_data_fetch_started(entity_type="identity")
            identity_started = time.monotonic()
            self._context = self.identity_client.fetch_context()
            self.message_client.set_streams(tuple(self._context.streams.values()))
            self.observability.log_data_fetch_completed(
                item_count=len(self._context.users) + len(self._context.streams),
                duration_ms=int((time.monotonic() - identity_started) * 1000),
                entity_type="identity",
            )

            uploader = PushUploader(
                datasource=self.name,
                timeout_ms=options.upload_timeout_ms if options else None,
                observability=self.observability,
            )
            self._upload_identities(uploader, options)
            self._upload_documents(uploader, options)
            self.observability.record_crawl_success()
        except Exception as error:
            self.observability.increment_counter("indexing_errors")
            self.observability.record_crawl_failure(type(error).__name__)
            self.observability.fail_execution(error)
            raise
        finally:
            self.observability.end_execution()

    def _upload_identities(self, uploader: PushUploader, options: ConnectorOptions | None) -> None:
        context = cast(ZulipCrawlContext, self._context)
        force_restart = True if options and options.force_restart else None
        users = [
            DatasourceUserDefinition(
                email=user.delivery_email or user.email,
                name=user.full_name,
                user_id=str(user.user_id),
                is_active=user.is_active,
            )
            for user in context.users.values()
            if not user.is_bot
        ]
        groups = [
            DatasourceGroupDefinition(name=_group_name(stream_id))
            for stream_id in context.private_members
        ]

        if users:
            uploader.bulk_index_users(
                users,
                upload_id=f"{self.generate_upload_id()}-users",
                batch_size=self.batch_size,
                force_restart_upload=force_restart,
            )
        if groups:
            uploader.bulk_index_groups(
                groups,
                upload_id=f"{self.generate_upload_id()}-groups",
                batch_size=self.batch_size,
                force_restart_upload=force_restart,
            )
        for stream_id, member_ids in context.private_members.items():
            memberships = [
                DatasourceBulkMembershipDefinition(member_user_id=str(member_id))
                for member_id in member_ids
            ]
            uploader.bulk_index_memberships(
                memberships,
                upload_id=f"{self.generate_upload_id()}-memberships-{stream_id}",
                batch_size=self.batch_size,
                force_restart_upload=force_restart,
                group=_group_name(stream_id),
            )

    def _upload_documents(self, uploader: PushUploader, options: ConnectorOptions | None) -> None:
        upload_id = f"{self.generate_upload_id()}-documents"
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
            batch = [cast(ZulipMessageRecord, next_item), *islice(iterator, self.batch_size - 1)]
            is_first_page = False
            batch_index += 1

    def _to_document(self, record: ZulipMessageRecord) -> DocumentDefinition:
        context = cast(ZulipCrawlContext, self._context)
        message = record.message
        if record.stream.invite_only and record.stream.stream_id not in context.private_members:
            raise ZulipCrawlError(
                f"Private channel {record.stream.stream_id} has no validated membership data"
            )
        message_id = _required_int(message, "id", "GET /messages")
        sender_id = _required_int(message, "sender_id", "GET /messages")
        timestamp = _required_int(message, "timestamp", "GET /messages")
        topic = message.get("subject")
        topic_name = topic if isinstance(topic, str) and topic else "general chat"
        sender = context.users.get(sender_id)
        author = (
            UserReferenceDefinition(datasource_user_id=str(sender_id), name=sender.full_name)
            if sender is not None and not sender.is_bot
            else UserReferenceDefinition(
                name=_optional_str(message, "sender_full_name") or "Unknown Zulip user"
            )
        )
        permissions = (
            DocumentPermissionsDefinition(allowed_groups=[_group_name(record.stream.stream_id)])
            if record.stream.invite_only
            else DocumentPermissionsDefinition(allow_all_datasource_users_access=True)
        )

        return DocumentDefinition(
            datasource=self.name,
            id=f"zulip-message-{message_id}",
            object_type="message",
            title=f"#{record.stream.name} > {topic_name}",
            view_url=f"{self.site}/#narrow/channel/{record.stream.stream_id}/near/{message_id}",
            body=ContentDefinition(
                mime_type="text/html",
                text_content=_required_str(message, "content", "GET /messages"),
            ),
            author=author,
            permissions=permissions,
            created_at=timestamp,
            updated_at=_optional_int(message, "last_edit_timestamp") or timestamp,
            tags=[record.stream.name, topic_name, "zulip-message"],
        )


def _response_object(response: Any, endpoint: str) -> Mapping[str, Any]:
    payload = response.data
    if not isinstance(payload, Mapping):
        raise ZulipCrawlError(f"{endpoint} returned a non-object response")
    if payload.get("result") not in (None, "success"):
        raise ZulipCrawlError(f"{endpoint} returned an unsuccessful result")
    return cast(Mapping[str, Any], payload)


def _object_list(payload: Mapping[str, Any], field: str, endpoint: str) -> list[Mapping[str, Any]]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ZulipCrawlError(f"{endpoint} returned invalid {field}")
    return cast(list[Mapping[str, Any]], value)


def _required_int(payload: Mapping[str, Any], field: str, endpoint: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ZulipCrawlError(f"{endpoint} returned invalid {field}")
    return value


def _optional_int(payload: Mapping[str, Any], field: str) -> int | None:
    value = payload.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _required_str(payload: Mapping[str, Any], field: str, endpoint: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ZulipCrawlError(f"{endpoint} returned invalid {field}")
    return value


def _optional_str(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value if isinstance(value, str) else None


def _group_name(stream_id: int) -> str:
    return f"zulip-channel-{stream_id}"
