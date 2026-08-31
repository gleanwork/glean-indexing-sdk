"""Full-crawl source client for Fantasy Premier League."""

import logging
import time
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from fpl_data import (
    AutomaticSubSummary,
    ChipSummary,
    ClubData,
    FixtureSummary,
    FPLData,
    LeagueData,
    ManagerGameweekData,
    ManagerHistorySummary,
    ManagerTeamData,
    PickSummary,
    PlayerData,
    PlayerSummary,
    PriorSeasonSummary,
    StandingSummary,
)

from glean.indexing.connectors import BaseStreamingDataClient
from glean.indexing.observability import ConnectorObservability
from glean.indexing.recipes.pull import (
    PullHttpClient,
    PullOptions,
    PullRetryOptions,
    TokenBucketRateLimiter,
)

logger = logging.getLogger("glean.connectors.fpl.source")

DEFAULT_BASE_URL = "https://fantasy.premierleague.com/api/"
DEFAULT_REQUESTS_PER_SECOND = 2.0
USER_AGENT = "Glean-Indexing-SDK-FPL-Connector/1.0"


class FPLSourceError(ValueError):
    """Raised when a required FPL response shape is missing or inconsistent."""


@dataclass(frozen=True)
class _ManagerContext:
    """Internal manager state reused while fetching gameweek picks."""

    manager_id: int
    manager_name: str
    team_name: str
    entered_events: frozenset[int]


class FPLDataClient(BaseStreamingDataClient[FPLData]):
    """Streams a complete, fail-closed crawl of one classic FPL league."""

    def __init__(
        self,
        league_id: int,
        *,
        base_url: str = DEFAULT_BASE_URL,
        requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
    ) -> None:
        if league_id <= 0:
            raise ValueError("league_id must be a positive integer")
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")

        self.league_id = league_id
        self.base_url = base_url
        self.requests_per_second = requests_per_second
        self.observability: ConnectorObservability | None = None

    def get_source_data(self, **kwargs: Any) -> Generator[FPLData, None, None]:
        """Yield the complete selected-league source state.

        Any required request or shape failure is allowed to propagate. A partial
        source result must never complete a full-crawl upload successfully.
        """
        if kwargs.get("since"):
            raise ValueError("The FPL connector supports full crawls only")

        crawl_time = int(time.time())
        limiter = TokenBucketRateLimiter(
            rate_per_second=self.requests_per_second,
            capacity=1.0,
        )
        options = PullOptions(
            timeout_seconds=30.0,
            rate_limit_timeout_seconds=120.0,
            retries=PullRetryOptions(
                max_attempts=4,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=30.0,
                backoff_multiplier=2.0,
                retry_connection_errors=True,
                respect_retry_after=True,
                jitter_seconds=0.5,
            ),
            mask_params=True,
        )

        with PullHttpClient(
            base_url=self.base_url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            options=options,
            rate_limiter=limiter,
            observability=self.observability,
        ) as http:
            bootstrap = self._fetch_dict(http, "/bootstrap-static/", "season bootstrap")
            fixtures = self._fetch_list(http, "/fixtures/", "fixtures")

            events = self._dict_items(bootstrap, "events", "season bootstrap")
            teams = self._dict_items(bootstrap, "teams", "season bootstrap")
            players = self._dict_items(bootstrap, "elements", "season bootstrap")
            positions = self._dict_items(bootstrap, "element_types", "season bootstrap")

            event_by_id = self._index_by_integer_id(events, "gameweek")
            team_by_id = self._index_by_integer_id(teams, "club")
            player_by_id = self._index_by_integer_id(players, "player")
            position_by_id = self._index_by_integer_id(positions, "position")
            fixtures_by_team = self._fixtures_by_team(fixtures, team_by_id, event_by_id)

            logger.info(
                "FPL season data fetched",
                extra={
                    "operation": "source_fetch_completed",
                    "entity_type": "season",
                    "player_count": len(players),
                    "club_count": len(teams),
                    "gameweek_count": len(events),
                    "fixture_count": len(fixtures),
                },
            )

            players_by_team: dict[int, list[PlayerSummary]] = defaultdict(list)
            for player in players:
                player_data = self._player_data(
                    player,
                    team_by_id,
                    position_by_id,
                    fixtures_by_team,
                    crawl_time,
                )
                players_by_team[self._required_int(player, "team", "player")].append(
                    PlayerSummary(
                        id=player_data["id"],
                        name=player_data["name"],
                        web_name=player_data["web_name"],
                        club=player_data["club"],
                        position=player_data["position"],
                    )
                )
                yield player_data

            for team in teams:
                team_id = self._required_int(team, "id", "club")
                yield self._club_data(
                    team,
                    sorted(players_by_team[team_id], key=lambda item: item["web_name"]),
                    fixtures_by_team.get(team_id, []),
                    crawl_time,
                )

            league_payload, standings_rows = self._fetch_all_standings(http)
            league_updated_at = self._timestamp(
                league_payload.get("last_updated_data"),
                crawl_time,
            )
            standings = [self._standing_summary(row) for row in standings_rows]
            league = self._required_dict(league_payload, "league", "league standings")
            yield LeagueData(
                kind="league",
                id=self._required_int(league, "id", "league"),
                name=self._required_str(league, "name", "league"),
                scoring=self._required_str(league, "scoring", "league"),
                start_event=self._required_int(league, "start_event", "league"),
                standings=standings,
                view_url=(
                    f"https://fantasy.premierleague.com/en/leagues/{self.league_id}/standings/c"
                ),
                updated_at=league_updated_at,
            )

            managers: list[_ManagerContext] = []
            for row in standings_rows:
                manager_id = self._required_int(row, "entry", "league standing")
                profile = self._fetch_dict(http, f"/entry/{manager_id}/", "manager profile")
                if self._required_int(profile, "id", "manager profile") != manager_id:
                    raise FPLSourceError("Manager profile ID did not match the standings entry")

                history = self._fetch_dict(
                    http,
                    f"/entry/{manager_id}/history/",
                    "manager history",
                )
                manager_context = self._manager_context(row, profile, event_by_id)
                managers.append(manager_context)
                yield self._manager_team_data(
                    row,
                    profile,
                    history,
                    team_by_id,
                    league_updated_at,
                )

            logger.info(
                "FPL league members fetched",
                extra={
                    "operation": "source_fetch_completed",
                    "entity_type": "manager_team",
                    "item_count": len(managers),
                    "standings_page_count": (len(standings_rows) + 49) // 50,
                },
            )

            published_events = sorted(
                (
                    event
                    for event in events
                    if self._required_timestamp(event, "deadline_time", "gameweek") <= crawl_time
                ),
                key=lambda event: self._required_int(event, "id", "gameweek"),
            )
            manager_gameweek_count = 0
            for event in published_events:
                event_id = self._required_int(event, "id", "gameweek")
                scoring_payload = self._fetch_dict(
                    http,
                    f"/event/{event_id}/live/",
                    "gameweek scoring",
                )
                scoring_by_player = self._scoring_by_player(scoring_payload)

                for manager in managers:
                    if event_id not in manager.entered_events:
                        continue
                    picks_payload = self._fetch_dict(
                        http,
                        f"/entry/{manager.manager_id}/event/{event_id}/picks/",
                        "manager gameweek picks",
                    )
                    yield self._manager_gameweek_data(
                        manager,
                        event,
                        picks_payload,
                        player_by_id,
                        team_by_id,
                        position_by_id,
                        scoring_by_player,
                        crawl_time,
                    )
                    manager_gameweek_count += 1

            logger.info(
                "FPL crawl source fetch completed",
                extra={
                    "operation": "source_fetch_completed",
                    "entity_type": "full_crawl",
                    "player_count": len(players),
                    "club_count": len(teams),
                    "manager_count": len(managers),
                    "published_gameweek_count": len(published_events),
                    "manager_gameweek_count": manager_gameweek_count,
                },
            )

    @staticmethod
    def _fetch_dict(http: PullHttpClient, path: str, label: str) -> dict[str, Any]:
        try:
            return http.get(path).json_dict()
        except (TypeError, ValueError) as error:
            raise FPLSourceError(f"Invalid {label} response: {error}") from error

    @staticmethod
    def _fetch_list(http: PullHttpClient, path: str, label: str) -> list[Any]:
        try:
            return http.get(path).json_list()
        except (TypeError, ValueError) as error:
            raise FPLSourceError(f"Invalid {label} response: {error}") from error

    def _fetch_all_standings(
        self,
        http: PullHttpClient,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        seen_manager_ids: set[int] = set()
        page_number = 1
        first_payload: dict[str, Any] | None = None

        while True:
            payload = (
                self._fetch_dict(
                    http,
                    f"/leagues-classic/{self.league_id}/standings/",
                    "league standings",
                )
                if page_number == 1
                else http.get(
                    f"/leagues-classic/{self.league_id}/standings/",
                    params={"page_standings": page_number},
                ).json_dict()
            )
            if first_payload is None:
                first_payload = payload

            league = self._required_dict(payload, "league", "league standings")
            if self._required_int(league, "id", "league") != self.league_id:
                raise FPLSourceError("League response ID did not match FPL_LEAGUE_ID")

            standings = self._required_dict(payload, "standings", "league standings")
            response_page = self._required_int(standings, "page", "league standings")
            if response_page != page_number:
                raise FPLSourceError(
                    f"Expected standings page {page_number}, received {response_page}"
                )

            page_rows = self._dict_items(standings, "results", "league standings")
            for row in page_rows:
                manager_id = self._required_int(row, "entry", "league standing")
                if manager_id in seen_manager_ids:
                    raise FPLSourceError(f"Duplicate manager entry {manager_id} in standings")
                seen_manager_ids.add(manager_id)
                rows.append(row)

            has_next = self._required_bool(standings, "has_next", "league standings")
            if not has_next:
                break
            if not page_rows:
                raise FPLSourceError("Standings claimed another page after an empty result page")
            page_number += 1

        if first_payload is None or not rows:
            raise FPLSourceError("Selected league returned no standings entries")
        return first_payload, rows

    def _fixtures_by_team(
        self,
        fixtures: list[Any],
        team_by_id: dict[int, dict[str, Any]],
        event_by_id: dict[int, dict[str, Any]],
    ) -> dict[int, list[FixtureSummary]]:
        output: dict[int, list[FixtureSummary]] = defaultdict(list)
        for index, value in enumerate(fixtures):
            fixture = self._as_dict(value, f"fixture[{index}]")
            home_id = self._required_int(fixture, "team_h", "fixture")
            away_id = self._required_int(fixture, "team_a", "fixture")
            if home_id not in team_by_id or away_id not in team_by_id:
                raise FPLSourceError("Fixture referenced an unknown club")

            event_id = self._optional_int(fixture.get("event"), "fixture.event")
            event_name = (
                self._required_str(event_by_id[event_id], "name", "gameweek")
                if event_id is not None and event_id in event_by_id
                else "Unscheduled"
            )
            kickoff = self._optional_str(fixture.get("kickoff_time"), "fixture.kickoff_time")
            finished = self._required_bool(fixture, "finished", "fixture")
            home_score = self._optional_int(fixture.get("team_h_score"), "fixture.team_h_score")
            away_score = self._optional_int(fixture.get("team_a_score"), "fixture.team_a_score")

            output[home_id].append(
                FixtureSummary(
                    event=event_id,
                    event_name=event_name,
                    opponent=self._required_str(team_by_id[away_id], "name", "club"),
                    kickoff_time=kickoff,
                    difficulty=self._required_int(
                        fixture,
                        "team_h_difficulty",
                        "fixture",
                    ),
                    is_home=True,
                    finished=finished,
                    score=self._fixture_score(home_score, away_score),
                )
            )
            output[away_id].append(
                FixtureSummary(
                    event=event_id,
                    event_name=event_name,
                    opponent=self._required_str(team_by_id[home_id], "name", "club"),
                    kickoff_time=kickoff,
                    difficulty=self._required_int(
                        fixture,
                        "team_a_difficulty",
                        "fixture",
                    ),
                    is_home=False,
                    finished=finished,
                    score=self._fixture_score(away_score, home_score),
                )
            )

        for summaries in output.values():
            summaries.sort(
                key=lambda item: (
                    item["event"] if item["event"] is not None else 999,
                    item["kickoff_time"] or "",
                )
            )
        return dict(output)

    def _player_data(
        self,
        player: dict[str, Any],
        team_by_id: dict[int, dict[str, Any]],
        position_by_id: dict[int, dict[str, Any]],
        fixtures_by_team: dict[int, list[FixtureSummary]],
        crawl_time: int,
    ) -> PlayerData:
        player_id = self._required_int(player, "id", "player")
        team_id = self._required_int(player, "team", "player")
        position_id = self._required_int(player, "element_type", "player")
        if team_id not in team_by_id or position_id not in position_by_id:
            raise FPLSourceError(f"Player {player_id} referenced an unknown club or position")

        first_name = self._required_str(player, "first_name", "player")
        second_name = self._required_str(player, "second_name", "player")
        known_name = self._optional_str(player.get("known_name"), "player.known_name")
        name = known_name or " ".join(part for part in (first_name, second_name) if part)
        now_cost = self._required_int(player, "now_cost", "player")
        team = team_by_id[team_id]
        position = position_by_id[position_id]
        upcoming = [
            fixture for fixture in fixtures_by_team.get(team_id, []) if not fixture["finished"]
        ]

        statistic_names = (
            "minutes",
            "starts",
            "goals_scored",
            "assists",
            "clean_sheets",
            "goals_conceded",
            "yellow_cards",
            "red_cards",
            "saves",
            "bonus",
            "bps",
            "influence",
            "creativity",
            "threat",
            "ict_index",
            "defensive_contribution",
            "expected_goals",
            "expected_assists",
            "expected_goal_involvements",
            "expected_goals_conceded",
            "transfers_in",
            "transfers_out",
            "dreamteam_count",
        )
        statistics = {name: player.get(name) for name in statistic_names if name in player}

        return PlayerData(
            kind="player",
            id=player_id,
            name=name,
            web_name=self._required_str(player, "web_name", "player"),
            club=self._required_str(team, "name", "club"),
            position=self._required_str(position, "singular_name", "position"),
            price=now_cost / 10,
            status=self._required_str(player, "status", "player"),
            news=self._optional_str(player.get("news"), "player.news") or "",
            selected_by_percent=self._required_str(player, "selected_by_percent", "player"),
            form=self._required_str(player, "form", "player"),
            points_per_game=self._required_str(player, "points_per_game", "player"),
            total_points=self._required_int(player, "total_points", "player"),
            statistics=statistics,
            fixtures=upcoming[:5],
            view_url=f"{self.base_url.rstrip('/')}/element-summary/{player_id}/",
            updated_at=self._timestamp(player.get("news_added"), crawl_time),
        )

    def _club_data(
        self,
        team: dict[str, Any],
        players: list[PlayerSummary],
        fixtures: list[FixtureSummary],
        crawl_time: int,
    ) -> ClubData:
        team_id = self._required_int(team, "id", "club")
        finished = [fixture for fixture in fixtures if fixture["finished"]]
        upcoming = [fixture for fixture in fixtures if not fixture["finished"]]
        return ClubData(
            kind="club",
            id=team_id,
            name=self._required_str(team, "name", "club"),
            short_name=self._required_str(team, "short_name", "club"),
            position=self._required_int(team, "position", "club"),
            played=self._required_int(team, "played", "club"),
            win=self._required_int(team, "win", "club"),
            draw=self._required_int(team, "draw", "club"),
            loss=self._required_int(team, "loss", "club"),
            points=self._required_int(team, "points", "club"),
            strength=self._optional_int(team.get("strength"), "club.strength"),
            strength_attack_home=self._required_int(team, "strength_attack_home", "club"),
            strength_attack_away=self._required_int(team, "strength_attack_away", "club"),
            strength_defence_home=self._required_int(team, "strength_defence_home", "club"),
            strength_defence_away=self._required_int(team, "strength_defence_away", "club"),
            players=players,
            recent_fixtures=list(reversed(finished[-5:])),
            upcoming_fixtures=upcoming[:5],
            view_url=f"{self.base_url.rstrip('/')}/bootstrap-static/#team-{team_id}",
            updated_at=crawl_time,
        )

    def _manager_context(
        self,
        standing: dict[str, Any],
        profile: dict[str, Any],
        event_by_id: dict[int, dict[str, Any]],
    ) -> _ManagerContext:
        manager_id = self._required_int(standing, "entry", "league standing")
        entered_values = profile.get("entered_events")
        entered_events: set[int] = set()
        if isinstance(entered_values, list):
            for value in entered_values:
                if isinstance(value, int) and not isinstance(value, bool):
                    entered_events.add(value)
                else:
                    raise FPLSourceError("manager profile entered_events contained a non-integer")
        if not entered_events:
            started_event = self._required_int(profile, "started_event", "manager profile")
            entered_events = {event_id for event_id in event_by_id if event_id >= started_event}

        return _ManagerContext(
            manager_id=manager_id,
            manager_name=self._required_str(standing, "player_name", "league standing"),
            team_name=self._required_str(standing, "entry_name", "league standing"),
            entered_events=frozenset(entered_events),
        )

    def _manager_team_data(
        self,
        standing: dict[str, Any],
        profile: dict[str, Any],
        history_payload: dict[str, Any],
        team_by_id: dict[int, dict[str, Any]],
        updated_at: int,
    ) -> ManagerTeamData:
        manager_id = self._required_int(standing, "entry", "league standing")
        favourite_team_id = self._optional_int(
            profile.get("favourite_team"),
            "manager profile.favourite_team",
        )
        favourite_club = None
        if favourite_team_id is not None and favourite_team_id in team_by_id:
            favourite_club = self._required_str(team_by_id[favourite_team_id], "name", "club")

        return ManagerTeamData(
            kind="manager_team",
            manager_id=manager_id,
            manager_name=self._required_str(standing, "player_name", "league standing"),
            team_name=self._required_str(standing, "entry_name", "league standing"),
            rank=self._required_int(standing, "rank", "league standing"),
            last_rank=self._required_int(standing, "last_rank", "league standing"),
            event_total=self._required_int(standing, "event_total", "league standing"),
            total=self._required_int(standing, "total", "league standing"),
            overall_rank=self._optional_int(
                profile.get("summary_overall_rank"),
                "manager profile.summary_overall_rank",
            ),
            favourite_club=favourite_club,
            history=self._manager_history(history_payload),
            chips=self._manager_chips(history_payload),
            prior_seasons=self._prior_seasons(history_payload),
            view_url=f"https://fantasy.premierleague.com/en/entry/{manager_id}/history",
            updated_at=updated_at,
        )

    def _manager_gameweek_data(
        self,
        manager: _ManagerContext,
        event: dict[str, Any],
        picks_payload: dict[str, Any],
        player_by_id: dict[int, dict[str, Any]],
        team_by_id: dict[int, dict[str, Any]],
        position_by_id: dict[int, dict[str, Any]],
        scoring_by_player: dict[int, dict[str, Any]],
        crawl_time: int,
    ) -> ManagerGameweekData:
        event_id = self._required_int(event, "id", "gameweek")
        raw_picks = self._dict_items(picks_payload, "picks", "manager gameweek picks")
        if len(raw_picks) != 15:
            raise FPLSourceError(
                f"Manager {manager.manager_id} gameweek {event_id} returned "
                f"{len(raw_picks)} picks instead of 15"
            )

        picks: list[PickSummary] = []
        for pick in raw_picks:
            player_id = self._required_int(pick, "element", "manager pick")
            if player_id not in player_by_id:
                raise FPLSourceError(f"Manager pick referenced unknown player {player_id}")
            player = player_by_id[player_id]
            team_id = self._required_int(player, "team", "player")
            position_id = self._required_int(player, "element_type", "player")
            multiplier = self._required_int(pick, "multiplier", "manager pick")
            score = scoring_by_player.get(player_id, {})
            player_points = self._optional_int(score.get("total_points"), "player score") or 0

            picks.append(
                PickSummary(
                    player_id=player_id,
                    player_name=self._required_str(player, "web_name", "player"),
                    club=self._required_str(team_by_id[team_id], "short_name", "club"),
                    position_name=self._required_str(
                        position_by_id[position_id],
                        "singular_name_short",
                        "position",
                    ),
                    squad_position=self._required_int(pick, "position", "manager pick"),
                    multiplier=multiplier,
                    is_captain=self._required_bool(pick, "is_captain", "manager pick"),
                    is_vice_captain=self._required_bool(
                        pick,
                        "is_vice_captain",
                        "manager pick",
                    ),
                    points=player_points,
                    effective_points=player_points * multiplier,
                )
            )

        entry_history = self._required_dict(
            picks_payload,
            "entry_history",
            "manager gameweek picks",
        )
        automatic_subs = self._automatic_subs(
            picks_payload,
            player_by_id,
        )
        active_chip_value = picks_payload.get("active_chip")
        active_chip = self._optional_str(active_chip_value, "manager picks.active_chip")

        return ManagerGameweekData(
            kind="manager_gameweek",
            manager_id=manager.manager_id,
            manager_name=manager.manager_name,
            team_name=manager.team_name,
            event=event_id,
            event_name=self._required_str(event, "name", "gameweek"),
            is_finished=self._optional_bool(event.get("finished"), "gameweek.finished"),
            points=self._required_int(entry_history, "points", "entry history"),
            total_points=self._required_int(entry_history, "total_points", "entry history"),
            overall_rank=self._optional_int(
                entry_history.get("overall_rank"),
                "entry history.overall_rank",
            ),
            active_chip=active_chip,
            picks=sorted(picks, key=lambda item: item["squad_position"]),
            automatic_subs=automatic_subs,
            view_url=(
                f"https://fantasy.premierleague.com/en/entry/{manager.manager_id}/event/{event_id}"
            ),
            updated_at=self._required_timestamp(event, "deadline_time", "gameweek"),
        )

    def _manager_history(
        self,
        payload: dict[str, Any],
    ) -> list[ManagerHistorySummary]:
        rows = self._dict_items(payload, "current", "manager history")
        history = [
            ManagerHistorySummary(
                event=self._required_int(row, "event", "manager history row"),
                points=self._required_int(row, "points", "manager history row"),
                total_points=self._required_int(row, "total_points", "manager history row"),
                rank=self._optional_int(row.get("rank"), "manager history row.rank"),
                overall_rank=self._optional_int(
                    row.get("overall_rank"),
                    "manager history row.overall_rank",
                ),
                bank=self._required_int(row, "bank", "manager history row"),
                value=self._required_int(row, "value", "manager history row"),
                transfers=self._required_int(
                    row,
                    "event_transfers",
                    "manager history row",
                ),
                transfer_cost=self._required_int(
                    row,
                    "event_transfers_cost",
                    "manager history row",
                ),
                bench_points=self._required_int(
                    row,
                    "points_on_bench",
                    "manager history row",
                ),
            )
            for row in rows
        ]
        return sorted(history, key=lambda row: row["event"])

    def _manager_chips(self, payload: dict[str, Any]) -> list[ChipSummary]:
        rows = self._dict_items(payload, "chips", "manager history")
        chips = [
            ChipSummary(
                name=self._required_str(row, "name", "manager chip"),
                event=self._required_int(row, "event", "manager chip"),
            )
            for row in rows
        ]
        return sorted(chips, key=lambda row: row["event"])

    def _prior_seasons(self, payload: dict[str, Any]) -> list[PriorSeasonSummary]:
        rows = self._dict_items(payload, "past", "manager history")
        return [
            PriorSeasonSummary(
                season_name=self._required_str(row, "season_name", "prior season"),
                total_points=self._required_int(row, "total_points", "prior season"),
                rank=self._required_int(row, "rank", "prior season"),
            )
            for row in rows
        ]

    def _automatic_subs(
        self,
        payload: dict[str, Any],
        player_by_id: dict[int, dict[str, Any]],
    ) -> list[AutomaticSubSummary]:
        rows = self._dict_items(payload, "automatic_subs", "manager gameweek picks")
        output: list[AutomaticSubSummary] = []
        for row in rows:
            player_in_id = self._required_int(row, "element_in", "automatic substitution")
            player_out_id = self._required_int(row, "element_out", "automatic substitution")
            if player_in_id not in player_by_id or player_out_id not in player_by_id:
                raise FPLSourceError("Automatic substitution referenced an unknown player")
            output.append(
                AutomaticSubSummary(
                    player_in=self._required_str(
                        player_by_id[player_in_id],
                        "web_name",
                        "player",
                    ),
                    player_out=self._required_str(
                        player_by_id[player_out_id],
                        "web_name",
                        "player",
                    ),
                )
            )
        return output

    def _scoring_by_player(
        self,
        payload: dict[str, Any],
    ) -> dict[int, dict[str, Any]]:
        rows = self._dict_items(payload, "elements", "gameweek scoring")
        output: dict[int, dict[str, Any]] = {}
        for row in rows:
            player_id = self._required_int(row, "id", "gameweek player score")
            if player_id in output:
                raise FPLSourceError(f"Duplicate player {player_id} in gameweek scoring")
            output[player_id] = self._required_dict(row, "stats", "gameweek player score")
        return output

    @staticmethod
    def _standing_summary(row: dict[str, Any]) -> StandingSummary:
        return StandingSummary(
            manager_id=FPLDataClient._required_int(row, "entry", "league standing"),
            manager_name=FPLDataClient._required_str(
                row,
                "player_name",
                "league standing",
            ),
            team_name=FPLDataClient._required_str(row, "entry_name", "league standing"),
            rank=FPLDataClient._required_int(row, "rank", "league standing"),
            last_rank=FPLDataClient._required_int(row, "last_rank", "league standing"),
            event_total=FPLDataClient._required_int(
                row,
                "event_total",
                "league standing",
            ),
            total=FPLDataClient._required_int(row, "total", "league standing"),
        )

    @staticmethod
    def _index_by_integer_id(
        rows: list[dict[str, Any]],
        label: str,
    ) -> dict[int, dict[str, Any]]:
        output: dict[int, dict[str, Any]] = {}
        for row in rows:
            item_id = FPLDataClient._required_int(row, "id", label)
            if item_id in output:
                raise FPLSourceError(f"Duplicate {label} ID {item_id}")
            output[item_id] = row
        return output

    @staticmethod
    def _dict_items(
        payload: dict[str, Any],
        key: str,
        label: str,
    ) -> list[dict[str, Any]]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise FPLSourceError(f"{label}.{key} must be a list")
        return [
            FPLDataClient._as_dict(item, f"{label}.{key}[{index}]")
            for index, item in enumerate(value)
        ]

    @staticmethod
    def _required_dict(payload: dict[str, Any], key: str, label: str) -> dict[str, Any]:
        return FPLDataClient._as_dict(payload.get(key), f"{label}.{key}")

    @staticmethod
    def _as_dict(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise FPLSourceError(f"{label} must be an object")
        return cast(dict[str, Any], value)

    @staticmethod
    def _required_int(payload: dict[str, Any], key: str, label: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise FPLSourceError(f"{label}.{key} must be an integer")
        return value

    @staticmethod
    def _optional_int(value: Any, label: str) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise FPLSourceError(f"{label} must be an integer or null")
        return value

    @staticmethod
    def _required_str(payload: dict[str, Any], key: str, label: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise FPLSourceError(f"{label}.{key} must be a string")
        return value

    @staticmethod
    def _optional_str(value: Any, label: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise FPLSourceError(f"{label} must be a string or null")
        return value

    @staticmethod
    def _required_bool(payload: dict[str, Any], key: str, label: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise FPLSourceError(f"{label}.{key} must be a boolean")
        return value

    @staticmethod
    def _optional_bool(value: Any, label: str) -> bool:
        if value is None:
            return False
        if not isinstance(value, bool):
            raise FPLSourceError(f"{label} must be a boolean or null")
        return value

    @staticmethod
    def _required_timestamp(payload: dict[str, Any], key: str, label: str) -> int:
        value = FPLDataClient._required_str(payload, key, label)
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError as error:
            raise FPLSourceError(f"{label}.{key} must be an ISO-8601 timestamp") from error

    @staticmethod
    def _timestamp(value: Any, fallback: int) -> int:
        if not isinstance(value, str) or not value:
            return fallback
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return fallback

    @staticmethod
    def _fixture_score(team_score: int | None, opponent_score: int | None) -> str | None:
        if team_score is None or opponent_score is None:
            return None
        return f"{team_score}-{opponent_score}"
