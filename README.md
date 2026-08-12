# Glean Indexing SDK

[![GA](https://img.shields.io/badge/-GA-F6F3EB?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMzIgMzIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0yNC4zMDA2IDIuOTU0MjdMMjAuNzY1NiAwLjE5OTk1MUwxNy45MDI4IDMuOTk1MjdDMTMuNTY1MyAxLjkzNDk1IDguMjMwMTkgMy4wODQzOSA1LjE5Mzk0IDcuMDA5ODNDMS42NTg4OCAxMS41NjQyIDIuNDgzIDE4LjExMzggNy4wMzczOCAyMS42NDg5QzguNzcyMzggMjIuOTkzNSAxMC43ODkzIDIzLjcwOTIgMTIuODI3OSAyMy44MTc3QzE2LjE0NjEgMjQuMDEyOCAxOS41MDc3IDIyLjYyNDggMjEuNjc2NSAxOS44MDU1QzI0LjczNDQgMTUuODggMjQuNTE3NSAxMC40MTQ4IDIxLjQ1OTYgNi43Mjc4OUwyNC4zMDA2IDIuOTU0MjdaTTE4LjExOTcgMTcuMDUxMkMxNi4xMDI4IDE5LjYzMiAxMi4zNzI1IDIwLjEwOTEgOS43NzAwMSAxOC4wOTIyQzcuMTg5MTkgMTYuMDc1MiA2LjcxMjA3IDEyLjMyMzMgOC43MjkwMSA5Ljc0MjQ2QzkuNzA0OTQgOC40ODQ1OCAxMS4xMTQ2IDcuNjgyMTQgMTIuNjc2MSA3LjQ4Njk2QzEzLjA0NDggNy40NDM1OCAxMy40MTM1IDcuNDIxOSAxMy43ODIyIDcuNDQzNThDMTQuOTc1IDcuNTA4NjUgMTYuMTI0NCA3Ljk0MjM5IDE3LjA3ODcgOC42Nzk3N0MxOS42NTk1IDEwLjcxODQgMjAuMTM2NiAxNC40NzAzIDE4LjExOTcgMTcuMDUxMloiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik0yNC41MTc2IDIxLjY5MjJDMjMuOTMyIDIyLjQ1MTMgMjMuMjgxNCAyMy4xMjM2IDIyLjU2NTcgMjMuNzUyNUMyMS44NzE3IDI0LjMzODEgMjEuMTEyNyAyNC44ODAzIDIwLjMxMDIgMjUuMzM1N0MxOS41Mjk1IDI1Ljc2OTUgMTguNjgzNyAyNi4xMzgyIDE3LjgzNzggMjYuNDIwMUMxNi45OTIgMjYuNzAyIDE2LjEwMjggMjYuODk3MiAxNS4yMTM3IDI3LjAwNTdDMTQuMzI0NSAyNy4xMTQxIDEzLjQzNTMgMjcuMTU3NSAxMi41MjQ0IDI3LjA5MjRDMTEuNjEzNSAyNy4wMjczIDEwLjcyNDMgMjYuODc1NSA5Ljg1Njg0IDI2LjY1ODdMOS42NjE2NSAyNy4zNzQzTDguNzcyNDYgMzAuOTk2MkM5LjkwMDIxIDMxLjI5OTggMTEuMDQ5NyAzMS40NzMzIDEyLjIyMDggMzEuNTZDMTIuMjY0MiAzMS41NiAxMi4zMjkyIDMxLjU2IDEyLjM3MjYgMzEuNTZDMTMuNTAwMyAzMS42MjUxIDE0LjY0OTggMzEuNTgxNyAxNS43NTU4IDMxLjQ1MTZDMTYuOTI3IDMxLjI5OTggMTguMDk4MSAzMS4wMzk1IDE5LjIyNTggMzAuNjcwOEMyMC4zNTM2IDMwLjMwMjIgMjEuNDU5NyAyOS44MjUgMjIuNTAwNyAyOS4yMzk1QzIzLjU2MzQgMjguNjUzOSAyNC41NjEgMjcuOTM4MiAyNS40OTM1IDI3LjE1NzVDMjYuNDQ3OCAyNi4zNTUgMjcuMzE1MyAyNS40NDQyIDI4LjA3NDQgMjQuNDQ2NUMyOC4xODI4IDI0LjMxNjQgMjguMjY5NSAyNC4xNjQ2IDI4LjM3OCAyNC4wMTI4TDI0Ljc3NzkgMjEuMzQ1MkMyNC42Njk0IDIxLjQ1MzcgMjQuNjA0NCAyMS41ODM4IDI0LjUxNzYgMjEuNjkyMloiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPg==&labelColor=343CED)](https://github.com/gleanwork/.github/blob/main/docs/repository-stability.md#ga)
[![PyPI version](https://badge.fury.io/py/glean-indexing-sdk.svg)](https://badge.fury.io/py/glean-indexing-sdk)

Build custom Glean connectors in Python. The SDK handles fetching, transforming, batching, and uploading your data to Glean's indexing APIs, so you write only the parts that are specific to your source.

📖 **[Full documentation](https://developers.glean.com/libraries/indexing-sdk)** on the Glean Developer site.

## Build one with an agent

The fastest path is to let a coding agent build the connector. Your agent installs it straight from this repository, which doubles as the plugin marketplace.

**Claude Code**

```bash
claude plugin marketplace add gleanwork/glean-indexing-sdk
claude plugin install glean-connector-builder@glean-indexing-sdk
```

**Codex**

```bash
codex plugin marketplace add gleanwork/glean-indexing-sdk
codex plugin add glean-connector-builder@glean-indexing-sdk
```

**Cursor** has no plugin CLI — open Dashboard → Plugins → Add Marketplace → Import from Repo, point it at `gleanwork/glean-indexing-sdk`, then install from Customize.

Then describe your source:

```text
I want to push my Webex data to Glean. Build a connector for me.
```

The agent explores the source's API, confirms a plan with you, generates the connector against this SDK, and tests it. See the [Indexing SDK overview](https://developers.glean.com/libraries/indexing-sdk) for what it does and what to review in the output.

## Or write it yourself

### Requirements

- Python >= 3.10
- A Glean instance and an [indexing API token](https://developers.glean.com/indexing/tag/Authentication/)

### Installation

```bash
pip install glean-indexing-sdk

# Optional cloud observability plugins
pip install "glean-indexing-sdk[aws]"   # CloudWatch logs + metrics
pip install "glean-indexing-sdk[gcp]"   # Cloud Logging + Cloud Monitoring
```

## Quickstart

Every connector has two parts: a **data client** that fetches from your source, and a **connector** that transforms the result into Glean documents. The flow is **fetch → transform → upload**; you implement `get_source_data()` and `transform()`, and the SDK does the rest.

Set your credentials:

```bash
export GLEAN_SERVER_URL="https://your-company-be.glean.com"
export GLEAN_INDEXING_API_TOKEN="your-indexing-api-token"
```

Then define and run a connector:

```python snippet=non_streaming/complete.py
from datetime import datetime
from typing import Any, List, Optional, Sequence, TypedDict

from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    IndexingMode,
    UserReferenceDefinition,
)


class WikiPage(TypedDict):
    id: str
    title: str
    content: str
    author: str
    updated_at: str
    url: str


class WikiDataClient(BaseDataClient[WikiPage]):
    """Fetches pages from the source system. Replace the body with a real API call."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url
        self.api_token = api_token

    def get_source_data(self, since: Optional[str] = None, **kwargs: Any) -> Sequence[WikiPage]:
        return [
            {
                "id": "page_123",
                "title": "Engineering Onboarding Guide",
                "content": "Welcome to the engineering team...",
                "author": "jane.smith@company.com",
                "updated_at": "2026-02-01T14:30:00Z",
                "url": f"{self.base_url}/pages/123",
            }
        ]


class CompanyWikiConnector(BaseDatasourceConnector[WikiPage]):
    """Transforms wiki pages into Glean documents."""

    configuration = CustomDatasourceConfig(
        name="company_wiki",
        display_name="Company Wiki",
        url_regex=r"https://wiki\.company\.com/.*",
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[WikiPage]) -> List[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=page["id"],
                title=page["title"],
                datasource=self.name,
                view_url=page["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=page["content"]),
                author=UserReferenceDefinition(email=page["author"]),
                # created_at / updated_at are epoch seconds, not ISO strings.
                updated_at=int(
                    datetime.fromisoformat(page["updated_at"].replace("Z", "+00:00")).timestamp()
                ),
            )
            for page in data
        ]


if __name__ == "__main__":
    connector = CompanyWikiConnector(
        name="company_wiki",
        data_client=WikiDataClient(
            base_url="https://wiki.company.com", api_token="your-wiki-token"
        ),
    )
    connector.configure_datasource()
    connector.index_data(mode=IndexingMode.FULL)
```

Test it without touching the network:

```python
from glean.indexing.testing import StaticDataClient, run_connector

result = run_connector(CompanyWikiConnector("company_wiki", StaticDataClient([...])))
result.assert_documents_posted(count=1, datasource="company_wiki")
```

## What's in the box

| Capability | What it gives you |
|---|---|
| [Connector types](https://developers.glean.com/libraries/indexing-sdk/concepts/connector-types) | Four base classes: in-memory, sync streaming, async streaming, and people/identity. |
| [Pull integrations](https://developers.glean.com/libraries/indexing-sdk/pull/http-client) | `PullHttpClient` with retries and backoff, link/offset/cursor pagination, and token-bucket rate limiting. |
| [Push & indexing](https://developers.glean.com/libraries/indexing-sdk/push/uploader) | `PushUploader` for documents, users, groups, memberships, and employees, with parallel batch uploads. |
| [Permissions](https://developers.glean.com/libraries/indexing-sdk/permissions) | Per-document ACLs and datasource identities so results respect who can see what. |
| [Testing](https://developers.glean.com/libraries/indexing-sdk/testing/overview) | Three phases: fully mocked, real-source-with-record/replay, and live end-to-end. |
| [Observability](https://developers.glean.com/libraries/indexing-sdk/observability) | Structured logging and metrics, with optional CloudWatch and Google Cloud plugins. |
| [Status & debugging](https://developers.glean.com/libraries/indexing-sdk/status-and-debugging) | `StatusClient` and `glean-idx document status` to answer "why isn't my document in search?" |
| [Deployment](https://developers.glean.com/libraries/indexing-sdk/deployment/overview) | `glean-idx deploy` generates Docker and Terraform for AWS or GCP. |
| [Connector Builder](https://developers.glean.com/libraries/indexing-sdk) | An agent plugin that builds a connector from a description of your source. |

## The CLI

One command, `glean-idx`, covers the whole loop.

```bash
glean-idx doctor                    # are my credentials right?
glean-idx validate ./my-connector   # is the plan complete, before writing code?
glean-idx test --phase all          # mocked, then real source, then live
glean-idx run                       # crawl for real
glean-idx datasource status --datasource my-source
glean-idx document status --datasource my-source --document Article doc-1
glean-idx deploy init --cloud gcp   # Docker and Terraform for a CronJob
```

Commands split into two kinds, and `glean-idx --help` says which is which.

Most need only `GLEAN_SERVER_URL` and `GLEAN_INDEXING_API_TOKEN`, so they run
anywhere, including with no install at all:

```bash
uvx --from glean-indexing-sdk glean-idx doctor
```

`run`, `test`, and `datasource configure` import your connector, so they run
inside the connector project with the SDK installed alongside your code:

```bash
uv run glean-idx run
```

Every command takes `--output json` for a stable envelope, `--yes` to skip
confirmations unattended, and returns a documented exit code — `3` for a
missing precondition, `4` for a Glean error, `5` for a validation failure. In
JSON mode the envelope goes to stdout whether it succeeded or not, so there is
one stream to read:

```bash
glean-idx datasource status --datasource my-source --output json | jq .data.documents
```

`glean-idx schema document` prints the JSON Schema your `transform()` has to
produce, and `glean-idx completion zsh` sets up tab completion.

## Indexing modes

```python
connector.index_data(mode=IndexingMode.FULL)         # re-index everything
connector.index_data(mode=IndexingMode.INCREMENTAL)  # only changes since the last crawl
```

A **full** crawl replaces the indexed state: documents absent from the run are deleted as stale. **Incremental** passes a `since` timestamp to your data client, but the SDK does not persist checkpoints — override `_get_last_crawl_timestamp()` on your connector to supply one. See [Indexing modes](https://developers.glean.com/libraries/indexing-sdk/concepts/indexing-modes).

## Contributing

This project uses [mise](https://mise.jdx.dev/) for toolchain management and `uv` for Python dependencies. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
mise run setup    # create venv and install dependencies
mise run test     # run all tests
mise run lint     # ruff, pyright, markdown-code
mise run lint:fix # auto-fix and format
```

Architecture notes for contributors live in [`docs/`](docs/).

## License

[MIT](LICENSE)
