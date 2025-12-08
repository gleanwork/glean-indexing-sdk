"""Data models for the wiki connector."""

from typing import List, TypedDict


class WikiPageData(TypedDict):
    """Type definition for wiki page data from the source system."""

    id: str
    title: str
    content: str
    author: str
    created_at: str
    updated_at: str
    url: str
    tags: List[str]
