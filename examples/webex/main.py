"""Local runner for the Webex connector (development convenience).

Reads config from ``.glean/.env`` (or the process environment) and runs a full
crawl. Run from THIS directory so the top-level module imports resolve:

    cd examples/webex && uv run python main.py

In deployment the CronJob uses the generated ``run.py`` instead, which imports
``WebexConnector`` and calls ``index_data`` directly.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from glean.indexing.models import IndexingMode

from connector import WebexConnector

logger = logging.getLogger("webex.main")

_ENV_PATH = Path(__file__).resolve().parent / ".glean" / ".env"


def _load_env_file(path: Path) -> None:
    """Populate os.environ from a simple KEY=VALUE .env file (no overrides)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _load_env_file(_ENV_PATH)

    if not os.environ.get("WEBEX_ACCESS_TOKEN"):
        logger.error("WEBEX_ACCESS_TOKEN is not set (checked env and %s)", _ENV_PATH)
        return 1
    if not (os.environ.get("GLEAN_SERVER_URL") and os.environ.get("GLEAN_INDEXING_API_TOKEN")):
        logger.error("GLEAN_SERVER_URL and GLEAN_INDEXING_API_TOKEN must be set")
        return 1

    # WebexConnector self-wires its data client from env and configures the
    # datasource before crawling.
    connector = WebexConnector(name="webex")
    logger.info("Starting Webex full crawl")
    connector.index_data(mode=IndexingMode.FULL)
    logger.info("Webex crawl complete. Source counters: %s", connector.data_client.counters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
