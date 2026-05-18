"""Webex source models used by the connector snippet."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WebexPerson:
    """Webex person record."""

    id: str
    emails: list[str] = field(default_factory=list)
    display_name: str | None = None
    nick_name: str | None = None
    status: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "WebexPerson":
        """Create a person from Webex API JSON."""
        return cls(
            id=str(data.get("id", "")),
            emails=list(data.get("emails") or []),
            display_name=data.get("displayName"),
            nick_name=data.get("nickName"),
            status=data.get("status"),
        )


@dataclass(frozen=True)
class WebexTeam:
    """Webex team record."""

    id: str
    name: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "WebexTeam":
        """Create a team from Webex API JSON."""
        return cls(id=str(data.get("id", "")), name=data.get("name"))


@dataclass(frozen=True)
class WebexMembership:
    """Webex room or team membership."""

    id: str
    person_id: str | None = None
    room_id: str | None = None
    team_id: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "WebexMembership":
        """Create a membership from Webex API JSON."""
        return cls(
            id=str(data.get("id", "")),
            person_id=data.get("personId"),
            room_id=data.get("roomId"),
            team_id=data.get("teamId"),
        )


@dataclass(frozen=True)
class WebexRoom:
    """Webex room record."""

    id: str
    title: str | None = None
    type: str = "group"
    team_id: str | None = None
    last_activity: str | None = None
    description: str | None = None
    is_public: bool = False

    @classmethod
    def from_api(cls, data: dict) -> "WebexRoom":
        """Create a room from Webex API JSON."""
        return cls(
            id=str(data.get("id", "")),
            title=data.get("title"),
            type=data.get("type", "group"),
            team_id=data.get("teamId"),
            last_activity=data.get("lastActivity"),
            description=data.get("description"),
            is_public=bool(data.get("isPublic", False)),
        )


@dataclass(frozen=True)
class WebexMessage:
    """Webex message record."""

    id: str
    room_id: str
    text: str | None = None
    markdown: str | None = None
    html: str | None = None
    person_id: str | None = None
    person_email: str | None = None
    parent_id: str | None = None
    created: str | None = None
    updated: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "WebexMessage":
        """Create a message from Webex API JSON."""
        return cls(
            id=str(data.get("id", "")),
            room_id=str(data.get("roomId", "")),
            text=data.get("text"),
            markdown=data.get("markdown"),
            html=data.get("html"),
            person_id=data.get("personId"),
            person_email=data.get("personEmail"),
            parent_id=data.get("parentId"),
            created=data.get("created"),
            updated=data.get("updated"),
        )


@dataclass
class WebexCrawlData:
    """All Webex data needed for one connector run."""

    people: list[WebexPerson] = field(default_factory=list)
    teams: list[WebexTeam] = field(default_factory=list)
    team_memberships: dict[str, list[WebexMembership]] = field(default_factory=dict)
    rooms: list[WebexRoom] = field(default_factory=list)
    room_memberships: dict[str, list[WebexMembership]] = field(default_factory=dict)
    messages_by_room: dict[str, list[WebexMessage]] = field(default_factory=dict)
