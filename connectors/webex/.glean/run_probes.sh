#!/usr/bin/env bash
# Read-only Webex API probes for connector exploration.
# Reads WEBEX_ACCESS_TOKEN from connectors/webex/.env. Never prints the token.
set -euo pipefail

ENV_FILE="$(dirname "$0")/../.env"
if [ ! -f "$ENV_FILE" ]; then echo "ERROR: $ENV_FILE not found" >&2; exit 1; fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
if [ -z "${WEBEX_ACCESS_TOKEN:-}" ]; then echo "ERROR: WEBEX_ACCESS_TOKEN not set" >&2; exit 1; fi

BASE="https://webexapis.com/v1"
AUTH="Authorization: Bearer ${WEBEX_ACCESS_TOKEN}"

# probe NAME METHOD PATH  -> prints status line, relevant headers, and body (jq if available)
probe() {
  local name="$1" path="$2"
  echo "==================== ${name} ===================="
  echo "GET ${path}"
  local hdr body
  hdr="$(mktemp)"; body="$(mktemp)"
  local code
  code="$(curl -sS -o "$body" -D "$hdr" -w '%{http_code}' -H "$AUTH" "${BASE}${path}")"
  echo "HTTP ${code}"
  # Show pagination + rate-limit headers only (redact nothing sensitive here)
  grep -iE '^(Link|Retry-After|X-RateLimit|Trackingid):' "$hdr" | sed 's/[Tt]rackingid:.*/Trackingid: <REDACTED>/' || true
  echo "--- body (truncated) ---"
  if command -v jq >/dev/null 2>&1; then
    jq -C '.' "$body" 2>/dev/null | head -c 4000 || head -c 2000 "$body"
  else
    head -c 3000 "$body"
  fi
  echo; echo
  rm -f "$hdr" "$body"
}

probe "AUTH TEST /people/me" "/people/me"
probe "LIST ROOMS" "/rooms?max=3&sortBy=lastactivity"
# capture first room id for dependent probes
ROOM_ID="$(curl -sS -H "$AUTH" "${BASE}/rooms?max=1&sortBy=lastactivity" | jq -r '.items[0].id // empty' 2>/dev/null || true)"
if [ -n "${ROOM_ID:-}" ]; then
  probe "LIST MESSAGES (first room)" "/messages?roomId=${ROOM_ID}&max=3"
  probe "LIST MEMBERSHIPS (first room)" "/memberships?roomId=${ROOM_ID}&max=3"
else
  echo "No room id found; skipping message/membership probes"
fi
probe "LIST PEOPLE (by id via me)" "/people?max=3"
