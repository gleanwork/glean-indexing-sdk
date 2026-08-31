# Glean FPL League connector

Local full-crawl connector for one Fantasy Premier League classic league. It indexes current players and clubs, a league overview, manager-team season overviews, and one public squad document per manager once a gameweek deadline has passed.

## Source coverage

- Public FPL endpoints only; no login or session cookie.
- League standings and every manager returned by league pagination.
- Public squads after each gameweek deadline, with live/provisional scoring until the gameweek finishes.
- Fixtures enrich player and club profiles.
- Every required source failure aborts the crawl before full-crawl finalization.

The FPL API is undocumented and unversioned. This connector is intended for the small, personal use case recorded in `.glean/connector_plan.md`.

## Local configuration

From this directory:

```bash
cp .env.example .env
```

Fill in:

- `FPL_LEAGUE_ID`: numeric league ID, such as the number in an FPL standings URL.
- `FPL_ALLOWED_USER_EMAIL`: the only Glean user allowed to see indexed documents.
- `GLEAN_SERVER_URL`: full Glean backend URL.
- `GLEAN_INDEXING_API_TOKEN`: indexing API token for the target datasource.

Optional:

- `FPL_REQUESTS_PER_SECOND`: defaults to `2.0`; keep this conservative because FPL publishes no rate limit.
- `FPL_LOG_LEVEL`: defaults to `INFO`.
- `FPL_API_BASE_URL`: defaults to `https://fantasy.premierleague.com/api/`; mainly useful for controlled testing.

Load the local environment in zsh:

```bash
set -a
source .env
set +a
```

## Validate and run

Use the repository's mise-managed `uv` executable:

```bash
mise exec -- uv run glean-idx validate .
mise exec -- uv run glean-idx datasource configure
mise exec -- uv run glean-idx run --mode full
```

Inspect the result:

```bash
mise exec -- uv run glean-idx datasource status --datasource gleanfplleague
mise exec -- uv run glean-idx document access \
  --datasource gleanfplleague \
  --object-type FPLLeague \
  --id "$FPL_LEAGUE_ID" \
  --user "$FPL_ALLOWED_USER_EMAIL"
```

The local `.env` file and test caches are ignored by git. Do not add session cookies or other FPL account credentials; they are not needed.
