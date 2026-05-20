from typing import TypedDict


class WebexUser(TypedDict, total=False):
    id: str
    displayName: str
    emails: list[str]


class WebexRoom(TypedDict, total=False):
    id: str
    title: str
    type: str
    teamId: str
    lastActivity: str
    created: str


class WebexTeam(TypedDict, total=False):
    id: str
    name: str
    created: str


class WebexTeamMembership(TypedDict, total=False):
    id: str
    teamId: str
    personId: str
    personEmail: str
    personDisplayName: str


class WebexMembership(TypedDict, total=False):
    id: str
    roomId: str
    personId: str
    personEmail: str
    personDisplayName: str
    isModerator: bool


class WebexMessage(TypedDict, total=False):
    id: str
    roomId: str
    roomType: str
    text: str
    markdown: str
    html: str
    personId: str
    personEmail: str
    created: str
    updated: str
    parentId: str


class WebexDocument(TypedDict):
    id: str
    title: str
    url: str
    body: str
    author_email: str
    created_at: str
    updated_at: str
    allowed_user_emails: list[str]
