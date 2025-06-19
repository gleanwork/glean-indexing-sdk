from typing import TypedDict


class ArticleData(TypedDict):
    """Type definition for knowledge base article data."""

    id: str
    title: str
    content: str
    author: str
    updated_at: str
    url: str
