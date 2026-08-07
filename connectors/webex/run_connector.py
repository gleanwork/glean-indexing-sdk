"""Run the Webex connector as a full crawl.

Reads credentials from the environment (or ``connectors/webex/.glean/.env``):
  - WEBEX_TOKEN          Webex API token (Compliance Officer in production)
  - WEBEX_BASE_URL       Webex API base URL (default https://webexapis.com/v1)
  - GLEAN_SERVER_URL     Glean instance URL (used by the SDK push client)
  - GLEAN_INDEXING_API_TOKEN   Glean indexing token

Usage:
    python -m connectors.webex.run_connector
"""

import logging
import os
from pathlib import Path

from glean.indexing.models import IndexingMode

from .webex_client import WebexComplianceClient
from .webex_connector import WebexConnector


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from .glean/.env if present (no external deps)."""
    env_path = Path(__file__).parent / ".glean" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _load_dotenv()

    token = os.environ.get("WEBEX_TOKEN")
    if not token:
        raise SystemExit("WEBEX_TOKEN is not set (put it in connectors/webex/.glean/.env)")
    base_url = os.environ.get("WEBEX_BASE_URL", "https://webexapis.com/v1")

    data_client = WebexComplianceClient(token=token, base_url=base_url)
    # Datasource name defaults to "webex"; override with WEBEX_DATASOURCE_NAME
    # (e.g. on a dev instance where the "webex" name is already taken).
    datasource_name = os.environ.get("WEBEX_DATASOURCE_NAME", "webex")
    connector = WebexConnector(name=datasource_name, data_client=data_client)

    connector.configure_datasource()
    connector.index_data(mode=IndexingMode.FULL)


if __name__ == "__main__":
    main()
