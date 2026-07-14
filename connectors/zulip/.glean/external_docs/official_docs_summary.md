# Zulip official API notes

Sources were confirmed on 2026-07-13.

## Authentication

Zulip REST requests use HTTP Basic authentication with the Zulip API email address as the username and an API key as the password. Requests target the organization's own base URL under `/api/v1`.

Source: https://zulip.com/api/rest

## Channels

`GET /streams` returns channels visible to the authenticated principal. `include_can_access_content=true` can request channels whose content is accessible; `include_all=true` expands metadata results when the principal has permission. Channel fields include `stream_id`, `name`, descriptions, creation time, archive state, and privacy flags.

Source: https://zulip.com/api/get-streams

## Messages

`GET /messages` supports ID-anchored ranges. A full historical scan can start with `anchor=oldest`, `num_before=0`, and a bounded `num_after`, then continue after the highest returned message ID until `found_newest=true`. Zulip recommends no more than 1,000 messages per request and enforces a maximum of 5,000.

Message visibility is relative to the authenticated principal. A user's history can omit channel messages sent before subscription. Shared-history narrows can expose public-channel history, while private-channel history remains permission-dependent. The endpoint returns message IDs, content, timestamps, sender IDs, channel IDs, and topics.

Source: https://zulip.com/api/get-messages

## Users and channel memberships

`GET /users` returns accessible organization users, including stable user IDs, API email addresses, names, active/deleted state, and role metadata.

`GET /streams/{stream_id}/members` returns active subscriber user IDs for a channel. This membership list can model private-channel access, subject to the authenticated principal being allowed to inspect the channel.

Sources:
- https://zulip.com/api/get-users
- https://zulip.com/api/get-subscribers

## Documentation-only limitations

No live Zulip organization or credentials were supplied. Exact server version, feature level, response shapes, rate-limit headers, accessible history, and permissions remain unverified.
