"""Local entrypoint for the Webex connector.

Runs a full crawl against a real Glean datasource. Loads `connectors/webex/.env`
if present, then configures the datasource and indexes.

Usage (from repo root):
    uv run python -m connectors.webex.run

Requires WEBEX_ACCESS_TOKEN, GLEAN_SERVER_URL, and GLEAN_INDEXING_API_TOKEN.
For local fetch-only validation without a real Glean upload, use the mock
harness in the connector's E2E smoke test instead.

The deployed CronJob does NOT use this file — `glean-deploy init` generates its
own `run.py`. This is for local runs only.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from glean.indexing.models import IndexingMode

from connectors.webex.connector import WebexConnector

logger = logging.getLogger(__name__)


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); does not override existing env."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    """Configure logging, load env, and run a full crawl."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    _load_dotenv(Path(__file__).with_name(".env"))

    connector = WebexConnector()
    connector.index_data(mode=IndexingMode.FULL)
    logger.info("Webex connector run complete.")


if __name__ == "__main__":
    main()
