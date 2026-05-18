"""Pagination helpers for source API pulls."""

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from glean.indexing.pull.http_client import PullHttpClient
from glean.indexing.pull.response import PullResponse


def parse_link_header_next(link_header: str | None) -> str | None:
    """Return the `rel=next` URL from an RFC 5988 Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part or "rel='next'" in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None


@dataclass(frozen=True)
class Page:
    """One page returned from a source API."""

    response: PullResponse
    items: list[Any]


class LinkHeaderPaginator:
    """Paginator for APIs that use `Link: <url>; rel="next"`."""

    def __init__(
        self,
        client: PullHttpClient,
        *,
        items_key: str = "items",
        next_url_parser: Callable[[str | None], str | None] = parse_link_header_next,
    ):
        """Initialize a Link-header paginator."""
        self.client = client
        self.items_key = items_key
        self.next_url_parser = next_url_parser

    def pages(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[Page]:
        """Yield pages until no `rel=next` link remains."""
        current_path = path_or_url
        current_params = params
        while True:
            response = self.client.get(current_path, params=current_params)
            body = response.json_dict()
            items = body.get(self.items_key, [])
            if not isinstance(items, list):
                raise TypeError(
                    f"Expected `{self.items_key}` to be a list, got {type(items).__name__}"
                )
            yield Page(response=response, items=items)

            next_url = self.next_url_parser(
                response.headers.get("link") or response.headers.get("Link")
            )
            if not next_url or not items:
                break
            current_path = next_url
            current_params = None

    def items(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Yield all items across pages."""
        for page in self.pages(path_or_url, params=params):
            yield from page.items
