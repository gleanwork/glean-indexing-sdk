# Webex Source Investigation

## Auth
- Test auth: read-only Webex bearer token (Compliance-Officer-capable), verified live on 2026-07-06.
- Production auth: org-wide via Compliance Officer token. Scopes: spark-compliance:events_read, spark-compliance:messages_read, spark-compliance:memberships_read, spark-compliance:rooms_read. Room-scoped alternative (bot/user): spark:people_read, spark:rooms_read, spark:messages_read, spark:memberships_read. Confirm exact strings on developer.webex.com.

## Source data model
- **Room (space):** group or direct. Title, timestamps, creator/owner, team linkage.
- **Message:** belongs to one room; text + optional html, files, mentionedPeople, parentId. Authored by personEmail.
- **Event:** compliance envelope {id, resource, type, actorId, created, data}; for resource=messages, `data` is the full message. Org-wide for Compliance Officers.
- **Membership:** person-to-room link with personEmail; readable for arbitrary org rooms with the compliance token.

## Sync model
- v1: full crawl only. Org-wide client pages /events?resource=messages within the allowed window, discovering rooms lazily.
- Incremental (follow-up): checkpoint the events window (from/to) and handle edit/delete event types.

## Constraints verified live
- Events API lookback capped at ~90 days: from=2026-04-08 -> 200, from=2026-04-01 -> 403. Client clamps over-old start_date forward with a warning.
- Org-wide events include rooms the token owner is not in.

## Permissions model
- allowed_users = current room members (from /memberships), which the compliance token can read for any org room.
- is_user_referenced_by_email=True on the datasource config.
- Fail-closed: room/membership read failure -> skip that room and its messages.

## Unknowns / risks
- Exact compliance scope strings (confirm on portal); Compliance Officer role required for org-wide.
- Rate limits: honor 429 + Retry-After. Cost scales with org message volume in the window.
- Messages older than ~90 days need Webex eDiscovery (out of scope).
- Message edits/deletions within the window not yet reconciled (follow-up).
