from typing import List, TypedDict


class WikiPageData(TypedDict):
    """Type definition for your source data structure."""

    id: str
    title: str
    content: str
    author: str
    created_at: str
    updated_at: str
    url: str
    tags: List[str]
