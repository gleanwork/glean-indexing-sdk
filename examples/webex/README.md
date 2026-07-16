# Webex Connector (Glean Indexing SDK)

Org-wide Webex connector that indexes **spaces** and **messages** into a Glean
custom datasource with **per-document ACLs** derived from Webex room membership.

Content is discovered through the Webex **compliance Events API** (`/events`),
which is the only org-wide message feed. See
[`.glean/connector_plan.md`](.glean/connector_plan.md) for the full design and
[`.glean/`](.glean/) for the API investigation artifacts.

## What it does

| Webex source | Glean document | ACL |
|---|---|---|
| Room / space (`GET /rooms/{id}`) | `Space` doc (`space:{roomId}`) | room members' emails |
| Message (`event.data`) | `Message` doc (`message:{messageId}`, `container=space:{roomId}`) | room members' emails |

- **Org-wide** via a Compliance Officer token (Events API).
- **Rolling ~90-day window** with full-crawl semantics — the Events feed only
  reaches back ~90 days (hard Webex platform cap), so each run refreshes a
  rolling window and prunes documents no longer in it.
- **Edits & deletes** within the window are reconciled: `type=updated` supersedes
  `type=created`; `type=deleted` message ids are dropped.
- ACLs reference users **by email** (`is_user_referenced_by_email=True`).

## Auth & scopes

Requires a **Compliance Officer** identity with:
`spark-compliance:events_read`, `spark-compliance:messages_read`,
`spark-compliance:rooms_read`, `spark-compliance:memberships_read`
(+ `spark:people_read`). A plain user/bot token only sees its own spaces and
cannot crawl org-wide.

## Configuration

Set these in `examples/webex/.glean/.env` (or the process environment):

```
WEBEX_ACCESS_TOKEN=<compliance officer token>
WEBEX_BASE_URL=https://webexapis.com/v1
GLEAN_SERVER_URL=https://<your-instance>-be.glean.com
GLEAN_INDEXING_API_TOKEN=<glean indexing token>
# optional
WEBEX_EVENTS_LOOKBACK_DAYS=89
```

## Run

From the repo root:

```bash
uv run python -m examples.webex.main
```

This configures the `webex` **test** datasource in Glean, then runs a full crawl.

## Files

- `models.py` — typed record shapes yielded by the data client.
- `data_client.py` — `WebexDataClient`: Events-API pull, pagination, 429 backoff, edit/delete reconciliation, per-room details + membership ACLs.
- `connector.py` — `WebexConnector`: datasource config + `transform()` to Glean documents.
- `main.py` — runnable entrypoint.

## Known limitations / follow-ups

- **~90-day history cap**: messages older than the Events window are not
  retrievable (would require Webex eDiscovery/archive export).
- **Incremental accumulation**: v1 is full-crawl only. Retaining history beyond
  the rolling window needs incremental mode (persisted cursor +
  `disable_stale_deletion_check`).
- **Attachments**: `files` are indexed as references only, not file contents.
- **Corporate TLS proxies**: if running behind an intercepting proxy, point
  Python at the proxy CA (e.g. `SSL_CERT_FILE`); the client uses `httpx` defaults.
- **Memory**: the crawl materializes the window's message events (grouped by
  room) before emitting; fine for typical orgs, revisit for very large ones.
