#!/usr/bin/env bash
# Connector-builder plugin update check (runs on SessionStart).
# Compares the installed plugin version against package.json on the release ref.
# SessionStart hook stdout is injected into the assistant's context, so the
# messages below are phrased as directives asking the assistant to relay the
# result to the user. Fails silently (never blocks session start) on any error.

REF="feature/v0-workstream"   # TODO: switch to "main" once releases land there
PLUGIN_ID="glean-connector-builder@glean-indexing-sdk-agent-plugin"
VERBOSE=1   # TEMP (test only): also relay the up-to-date/skip case. Set 0 for production.

local_v=$(claude plugin list 2>/dev/null \
  | awk -v p="$PLUGIN_ID" '$0 ~ p {f=1} f && /Version:/ {print $2; exit}')

remote_v=$(curl -fsS --max-time 3 \
  "https://raw.githubusercontent.com/gleanwork/glean-indexing-sdk/$REF/package.json" 2>/dev/null \
  | grep '"version"' | head -1 | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')

if [ -z "$local_v" ] || [ -z "$remote_v" ]; then
  [ "$VERBOSE" = 1 ] && echo "SYSTEM (connector-builder update check): could not determine versions (installed='$local_v' latest='$remote_v'); skipping. No need to mention this to the user."
  exit 0
fi

if [ "$local_v" != "$remote_v" ]; then
  newest=$(printf '%s\n%s\n' "$local_v" "$remote_v" | sort -V | tail -1)
  if [ "$newest" = "$remote_v" ]; then
    echo "SYSTEM (connector-builder update check): a newer version of the glean-connector-builder plugin is available (installed $local_v, latest $remote_v). Please tell the user, at the start of your reply, that an update is available and that they can get it by running: npm run build:plugins && claude plugin update $PLUGIN_ID"
    exit 0
  fi
fi

[ "$VERBOSE" = 1 ] && echo "SYSTEM (connector-builder update check): the glean-connector-builder plugin is up-to-date (installed $local_v, latest $remote_v). Briefly confirm this to the user."
exit 0
