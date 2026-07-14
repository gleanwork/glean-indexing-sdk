# Zulip API inventory

Exploration mode: official documentation only. No live API calls were made.

## Authentication and base URL

Requests target `https://<organization-host>/api/v1` and use HTTP Basic authentication with a Zulip API email address and API key. The production connector should receive the organization URL, email, and API key through environment variables.

Source: https://zulip.com/api/rest

## In-scope endpoints

### GET `/api/v1/streams`

Discovers channels visible to the connector principal. The connector will request `include_can_access_content=true` and exclude archived channels by default. The response is not documented as paginated.

Important fields: `stream_id`, `name`, `description`, `rendered_description`, `date_created`, `is_archived`, `invite_only`, and `is_web_public`.

Source: https://zulip.com/api/get-streams

### GET `/api/v1/messages`

Fetches channel messages using a per-channel narrow. The full crawl starts at `anchor=oldest` with `num_before=0`, `num_after=1000`, and `apply_markdown=true`. Subsequent requests use the highest returned message ID as the anchor with `include_anchor=false`. Crawling stops when `found_newest=true`.

Zulip recommends at most 1,000 messages per request and rejects requests over 5,000. The connector must surface `history_limited=true` because it indicates source-side retention or plan restrictions.

Important fields: `id`, `content`, `content_type`, `sender_id`, `sender_full_name`, `stream_id`, `subject` (topic), `timestamp`, and `last_edit_timestamp`.

Visibility caveat: message history is relative to the authenticated principal. Newly created bots usually lack subscriptions, and a user's history may not contain messages from before subscription. For this first version, the deployment owner must use a dedicated account with access to every intended channel and validate history completeness.

Source: https://zulip.com/api/get-messages

### GET `/api/v1/users`

Returns accessible organization users without documented pagination. Stable datasource identity keys use `user_id`, not email, because Zulip can return API-only placeholder email addresses when real email visibility is restricted.

Important fields: `user_id`, `email`, `delivery_email`, `full_name`, `is_active`, `is_bot`, `is_guest`, `is_deleted`, and `avatar_url`.

Source: https://zulip.com/api/get-users

### GET `/api/v1/streams/{stream_id}/members`

Returns active subscriber user IDs for a channel. For private channels, these IDs will become a channel group and memberships used by message permissions. The endpoint is not documented as paginated.

Source: https://zulip.com/api/get-subscribers

## Entity and permission model

- One Glean document per Zulip channel message.
- One datasource user per accessible Zulip human user. Bots remain message authors but are not expected to map to Glean people identities.
- One datasource group per private Zulip channel.
- One datasource membership per active subscriber of each private channel.
- Public-channel message permissions use datasource-wide visibility; private-channel messages allow the matching channel group.

The exact SDK representation of datasource-wide/public access will be verified against the installed SDK models during implementation.

## Skipped endpoints

- Direct messages: excluded by confirmed first-version scope.
- Attachments: excluded from the first version; links embedded in rendered message content remain available.
- Reactions and message edit history: excluded because the latest rendered message is sufficient for search.
- Events API: excluded because AI-built connectors currently use full crawls rather than incremental synchronization.
- Archived-channel detail endpoints: excluded by default; archived content policy needs explicit product confirmation.

## Unverified behavior

Without live credentials, the following remain lower-confidence: organization feature level, actual response shapes, rate-limit headers and quotas, private-channel subscriber visibility, historical completeness, and treatment of deleted messages.
