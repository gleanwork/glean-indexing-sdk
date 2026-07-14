# Zulip source investigation

## Confirmed scope

The first version indexes accessible channel messages, channels, and users. Direct messages are excluded. The workflow supports a full crawl only.

## Source model

- Channels are stable objects keyed by integer `stream_id`.
- Messages are stable objects keyed by integer message `id`; channel messages include `stream_id` and a topic in `subject`.
- Users are stable objects keyed by integer `user_id`.
- Channel subscriber lists contain active user IDs and can model private-channel access.

Sources:
- https://zulip.com/api/get-streams
- https://zulip.com/api/get-messages
- https://zulip.com/api/get-users
- https://zulip.com/api/get-subscribers

## Authentication

- Test auth: No test credentials were supplied; API exploration used official documentation only.
- Production auth: HTTP Basic authentication supplied through `ZULIP_EMAIL` and `ZULIP_API_KEY`, with `ZULIP_SITE` providing the organization base URL.
- Required permissions: The dedicated Zulip principal must have content access to every intended channel and permission to list each private channel's subscribers.
- Secret handling: Never persist or log API keys, Basic authorization headers, Glean tokens, cookies, or message request bodies.

## Full-crawl behavior

1. Fetch accessible, non-archived channels.
2. Fetch organization users.
3. Fetch subscriber IDs for private channels.
4. Fetch message history independently for every channel with an ID-anchored, oldest-to-newest page loop.
5. Transform each message into a Glean document.
6. Replace datasource users, private-channel groups, memberships, and documents using bulk full-crawl APIs.

Message edits are naturally reflected because every full crawl remaps the latest returned message. Deletions are handled by replacement semantics when previously indexed records are absent from a later complete crawl.

## Permission model

Public channel messages are intended to be visible datasource-wide. Private channel messages are restricted to a datasource group keyed by channel ID, populated from `GET /streams/{stream_id}/members`.

This model has two deployment risks:

1. Zulip history is relative to the connector principal, so the account may not see messages from before it joined a channel.
2. Subscriber lists include Zulip users, but Glean access resolution requires reliable identity mapping. `delivery_email` may be hidden and `email` may be an API-only placeholder. The deployment owner must validate that indexed datasource users resolve to the intended Glean users before enabling private content.

The connector must fail closed for private channels when memberships cannot be fetched or mapped; it must not downgrade them to public visibility.

## Pagination, limits, and errors

Messages support ID-anchored range retrieval and expose `found_newest`, `found_oldest`, and `history_limited`. Use pages of at most 1,000 messages and retry transient 429/5xx responses according to `Retry-After` when available. Exact rate limits are not stated in the reviewed endpoint documentation and remain unverified.

Channels, users, and subscriber lists are not documented as paginated.

## Incremental and deletion signals

Incremental crawling is out of scope. Zulip's events API could support future change processing, but durable cursor recovery and deletion handling require developer-owned design. The full crawl relies on bulk replacement for stale records.

## Load and operational unknowns

No organization statistics were supplied. Expected channel count, message count, average rendered message size, API quota, freshness target, and hosting owner are unknown. The provisional recommendation is a daily full crawl, revisited after measuring one complete run.

## Required pre-production verification

- Probe all in-scope endpoints against the target Zulip version.
- Confirm the connector account can retrieve complete intended history.
- Confirm `history_limited` is false or explicitly accept limited history.
- Verify public/private channel classification and subscriber visibility.
- Verify datasource user identity resolution before uploading private messages.
- Measure record count, payload size, request count, duration, and retry behavior.
