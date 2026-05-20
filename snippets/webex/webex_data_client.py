import os
from collections import defaultdict
from collections.abc import Generator, Iterable

from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.pull import (
    BearerTokenAuth,
    LinkHeaderPaginator,
    PullHttpClient,
    PullOptions,
    RateLimitConfig,
)

from .webex_data import (
    WebexDocument,
    WebexMembership,
    WebexMessage,
    WebexRoom,
    WebexTeam,
    WebexTeamMembership,
    WebexUser,
)


WEBEX_BASE_URL = "https://webexapis.com/v1"


class WebexDataClient(BaseStreamingDataClient[WebexDocument]):
    """Pulls Webex Messaging content visible to the configured bearer token."""

    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = WEBEX_BASE_URL,
        max_rooms: int | None = None,
    ):
        self.max_rooms = max_rooms
        self.client = PullHttpClient(
            base_url=base_url,
            auth=BearerTokenAuth(access_token),
            options=PullOptions(mask_logs=True),
            rate_limiter=RateLimitConfig(
                calls=240,
                period_seconds=60,
                strategy="rolling",
            ).create_limiter(),
        )
        self.paginator = LinkHeaderPaginator(self.client, items_key="items")

    @classmethod
    def from_env(cls) -> "WebexDataClient":
        """Create a client from local environment variables."""
        access_token = os.environ["WEBEX_ACCESS_TOKEN"]
        max_rooms = os.environ.get("WEBEX_MAX_ROOMS")
        return cls(access_token, max_rooms=int(max_rooms) if max_rooms else None)

    def get_source_data(self, since: str | None = None) -> Generator[WebexDocument, None, None]:
        """Yield room summary docs and message-thread docs one room at a time."""
        for index, room in enumerate(self._rooms()):
            if self.max_rooms is not None and index >= self.max_rooms:
                break
            if since and room.get("lastActivity") and room["lastActivity"] < since:
                continue

            memberships = list(self._memberships(room["id"]))
            allowed_user_emails = sorted(
                email
                for email in {membership.get("personEmail", "") for membership in memberships}
                if email
            )
            yield self._room_document(room, allowed_user_emails)

            messages = list(self._messages(room["id"]))
            yield from self._message_thread_documents(room, messages, allowed_user_emails)

    def get_identity_data(
        self,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
        """Return datasource users, groups, and memberships for Webex identities."""
        users_by_id: dict[str, dict[str, object]] = {}
        groups: list[dict[str, object]] = []
        memberships: list[dict[str, object]] = []

        for team in self._teams():
            team_group_name = self._team_group_name(team["id"])
            groups.append({"name": team_group_name, "displayName": team.get("name") or team["id"]})
            for membership in self._team_memberships(team["id"]):
                self._remember_membership_user(users_by_id, membership)
                membership_definition = self._membership_definition(team_group_name, membership)
                if membership_definition:
                    memberships.append(membership_definition)

        for index, room in enumerate(self._rooms()):
            if self.max_rooms is not None and index >= self.max_rooms:
                break
            room_group_name = self._room_group_name(room["id"])
            groups.append({"name": room_group_name, "displayName": room.get("title") or room["id"]})
            for membership in self._memberships(room["id"]):
                self._remember_membership_user(users_by_id, membership)
                membership_definition = self._membership_definition(room_group_name, membership)
                if membership_definition:
                    memberships.append(membership_definition)

        return list(users_by_id.values()), groups, memberships

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def _people(self) -> Iterable[WebexUser]:
        yield from self.paginator.items("/people", params={"max": 1000})

    def _teams(self) -> Iterable[WebexTeam]:
        yield from self.paginator.items("/teams", params={"max": 1000})

    def _team_memberships(self, team_id: str) -> Iterable[WebexTeamMembership]:
        yield from self.paginator.items("/team/memberships", params={"teamId": team_id, "max": 1000})

    def _rooms(self) -> Iterable[WebexRoom]:
        yield from self.paginator.items("/rooms", params={"max": 1000})

    def _memberships(self, room_id: str) -> Iterable[WebexMembership]:
        yield from self.paginator.items("/memberships", params={"roomId": room_id, "max": 1000})

    def _messages(self, room_id: str) -> Iterable[WebexMessage]:
        params: dict[str, object] = {"roomId": room_id, "max": 1000}
        yield from self.paginator.items("/messages", params=params)

    def _room_document(self, room: WebexRoom, allowed_user_emails: list[str]) -> WebexDocument:
        room_title = room.get("title") or room["id"]
        updated_at = room.get("lastActivity") or room.get("created") or ""
        return {
            "id": f"room:{room['id']}",
            "title": f"Webex room: {room_title}",
            "url": self._room_url(room["id"]),
            "body": f"Webex room: {room_title}",
            "author_email": "",
            "created_at": room.get("created", ""),
            "updated_at": updated_at,
            "allowed_user_emails": allowed_user_emails,
        }

    def _message_thread_documents(
        self,
        room: WebexRoom,
        messages: list[WebexMessage],
        allowed_user_emails: list[str],
    ) -> Iterable[WebexDocument]:
        replies_by_parent: dict[str, list[WebexMessage]] = defaultdict(list)
        root_messages: list[WebexMessage] = []
        known_message_ids = {message["id"] for message in messages if "id" in message}

        for message in messages:
            parent_id = message.get("parentId")
            if parent_id and parent_id in known_message_ids:
                replies_by_parent[parent_id].append(message)
            else:
                root_messages.append(message)

        for root in root_messages:
            thread_messages = [root, *replies_by_parent.get(root["id"], [])]
            body = "\n\n---\n\n".join(self._message_text(message) for message in thread_messages)
            title = self._message_title(root, room)
            created_at = root.get("created", "")
            updated_at = max(
                (message.get("updated") or message.get("created") or "" for message in thread_messages),
                default=created_at,
            )
            yield {
                "id": f"message:{root['id']}",
                "title": title,
                "url": self._room_url(root.get("roomId") or room["id"]),
                "body": body,
                "author_email": root.get("personEmail", ""),
                "created_at": created_at,
                "updated_at": updated_at,
                "allowed_user_emails": allowed_user_emails,
            }

    def _message_title(self, message: WebexMessage, room: WebexRoom) -> str:
        text = self._message_text(message).replace("\n", " ").strip()
        if text:
            return text[:80]
        return f"Webex message in {room.get('title') or room['id']}"

    def _message_text(self, message: WebexMessage) -> str:
        return (
            message.get("markdown")
            or message.get("text")
            or message.get("html")
            or "(message has no text body)"
        )

    def _room_url(self, room_id: str) -> str:
        return f"https://app.webex.com/rooms/{room_id}"

    def _user_definition(self, user: WebexUser) -> dict[str, object]:
        email = next(iter(user.get("emails", [])), "")
        return {
            "datasourceUserId": user["id"],
            "email": email,
            "name": user.get("displayName") or email or user["id"],
        }

    def _remember_membership_user(
        self,
        users_by_id: dict[str, dict[str, object]],
        membership: WebexMembership | WebexTeamMembership,
    ) -> None:
        person_id = membership.get("personId")
        email = membership.get("personEmail", "")
        if not person_id or not email:
            return
        users_by_id[person_id] = {
            "datasourceUserId": person_id,
            "email": email,
            "name": membership.get("personDisplayName") or email,
        }

    def _membership_definition(
        self,
        group_name: str,
        membership: WebexMembership | WebexTeamMembership,
    ) -> dict[str, object] | None:
        member_user_id = membership.get("personEmail") or membership.get("personId")
        if not member_user_id:
            return None
        return {
            "groupName": group_name,
            "memberUserId": member_user_id,
        }

    def _room_group_name(self, room_id: str) -> str:
        return f"room:{room_id}"

    def _team_group_name(self, team_id: str) -> str:
        return f"team:{team_id}"
