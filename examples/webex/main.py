"""Run the Webex connector.

Environment variables:
    WEBEX_API_TOKEN         Webex bearer token (production auth model TBD).
    GLEAN_SERVER_URL        Glean backend URL (e.g. https://acme-be.glean.com).
    GLEAN_INDEXING_API_TOKEN  Glean indexing API token.

Usage:
    uv run python -m examples.webex.main            # configure + full index
    uv run python -m examples.webex.main --dry-run  # fetch + transform only, no upload
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from examples.webex.connector import WebexConnector
from examples.webex.data_client import WebexDataClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Webex Glean connector.")
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
