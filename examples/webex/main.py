"""Run the Webex connector.

Environment variables:
    WEBEX_API_TOKEN           Webex bearer token (production auth model TBD).
    GLEAN_SERVER_URL          Glean backend URL (e.g. https://acme-be.glean.com).
    GLEAN_INDEXING_API_TOKEN  Glean indexing API token.

Usage:
    # Org-wide crawl via the compliance Events API (Compliance Officer token):
    uv run python -m examples.webex.main --org-wide --start-date 2026-01-01T00:00:00Z

    # Room-scoped crawl (bot/user token; only rooms the token owner is in):
    uv run python -m examples.webex.main

    # Fetch + transform only, no upload:
    uv run python -m examples.webex.main --org-wide --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from examples.webex.connector import WebexConnector
from examples.webex.data_client import WebexDataClient, WebexEventsDataClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Webex Glean connector.")
    parser.add_argument(
        "--org-wide",
        action="store_true",
        help="Crawl the whole org via the compliance Events API (Compliance Officer token).",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="ISO-8601 'from' bound for the org-wide crawl (default: Webex ~90-day window).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform only; print document counts without uploading to Glean.",
    )
    parser.add_argument(
        "--include-direct",
        action="store_true",
        help="Also index direct (1:1) rooms. Off by default.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    token = os.environ.get("WEBEX_API_TOKEN")
    if not token:
        print("WEBEX_API_TOKEN is not set.", file=sys.stderr)
        return 2

    room_types = ("group", "direct") if args.include_direct else ("group",)
    if args.org_wide:
        data_client = WebexEventsDataClient(
            api_token=token, start_date=args.start_date, room_types=room_types
        )
    else:
        data_client = WebexDataClient(api_token=token, room_types=room_types)
    connector = WebexConnector(data_client)

    if args.dry_run:
        documents = list(connector.transform(list(connector.get_data())))
        spaces = sum(1 for d in documents if d.object_type == "Space")
        messages = sum(1 for d in documents if d.object_type == "Message")
        print(f"[dry-run] {len(documents)} documents ({spaces} spaces, {messages} messages)")
        return 0

    connector.configure_datasource()
    connector.index_data()
    print("Webex indexing complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
