from typing import TypedDict


class ArticleData(TypedDict):
    """Knowledge base article returned by the source API."""

    id: str
    title: str
    content: str
    author: str
    allowed_users: list[str]
    updated_at: str
    url: str
