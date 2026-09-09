"""Glean connector for a private Fantasy Premier League mini-league."""

import logging
import os
from collections import Counter
from collections.abc import Sequence
from html import escape
from typing import Any, cast

from fpl_data import (
    ClubData,
    FixtureSummary,
    FPLData,
    LeagueData,
    ManagerGameweekData,
    ManagerTeamData,
    PickSummary,
    PlayerData,
)
from fpl_data_client import (
    DEFAULT_BASE_URL,
    DEFAULT_REQUESTS_PER_SECOND,
    FPLDataClient,
)

from glean.api_client.models import (
    DatasourceCategory,
    DatasourceUserDefinition,
    DocumentPermissionsDefinition,
    ObjectDefinition,
)
from glean.indexing.connectors import (
    BaseStreamingDataClient,
    BaseStreamingDatasourceConnector,
)
from glean.indexing.models import (
    ConnectorOptions,
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    IndexingMode,
    UserReferenceDefinition,
)
from glean.indexing.observability import setup_connector_logging
from glean.indexing.push import PushUploader

logger = logging.getLogger("glean.connectors.fpl")

DATASOURCE_NAME = "gleanfplleague"
DISPLAY_NAME = "Glean FPL League"

PLAYER_OBJECT_TYPE = "Player"
CLUB_OBJECT_TYPE = "Club"
LEAGUE_OBJECT_TYPE = "FPLLeague"
MANAGER_TEAM_OBJECT_TYPE = "ManagerTeam"
MANAGER_GAMEWEEK_OBJECT_TYPE = "ManagerGameweek"

OBJECT_TYPES = (
    PLAYER_OBJECT_TYPE,
    CLUB_OBJECT_TYPE,
    LEAGUE_OBJECT_TYPE,
    MANAGER_TEAM_OBJECT_TYPE,
    MANAGER_GAMEWEEK_OBJECT_TYPE,
)

STATUS_LABELS = {
    "a": "Available",
    "d": "Doubtful",
    "i": "Injured",
    "n": "Not available",
    "s": "Suspended",
    "u": "Unavailable",
}


class FPLConnector(BaseStreamingDatasourceConnector[FPLData]):
    """Indexes FPL players, clubs, and one selected league as Glean documents."""

    configuration = CustomDatasourceConfig(
        name=DATASOURCE_NAME,
        display_name=DISPLAY_NAME,
        datasource_category=DatasourceCategory.PUBLISHED_CONTENT,
        home_url="https://fantasy.premierleague.com/",
        url_regex=r"https://fantasy\.premierleague\.com/.*",
        is_user_referenced_by_email=True,
        object_definitions=[
            ObjectDefinition(name=PLAYER_OBJECT_TYPE, display_label="FPL Player"),
            ObjectDefinition(name=CLUB_OBJECT_TYPE, display_label="Premier League Club"),
            ObjectDefinition(name=LEAGUE_OBJECT_TYPE, display_label="FPL League"),
            ObjectDefinition(name=MANAGER_TEAM_OBJECT_TYPE, display_label="FPL Manager Team"),
            ObjectDefinition(
                name=MANAGER_GAMEWEEK_OBJECT_TYPE,
                display_label="FPL Manager Gameweek",
            ),
        ],
    )

    def __init__(
        self,
        *,
        league_id: int | None = None,
        allowed_user_email: str | None = None,
        data_client: BaseStreamingDataClient[FPLData] | None = None,
    ) -> None:
        resolved_email = allowed_user_email or _required_environment("FPL_ALLOWED_USER_EMAIL")
        if "@" not in resolved_email:
            raise ValueError("FPL_ALLOWED_USER_EMAIL must be a valid email address")

        setup_connector_logging(
            DATASOURCE_NAME,
            log_level=os.getenv("FPL_LOG_LEVEL", "INFO"),
            use_structured_logging=True,
        )

        if data_client is None:
            resolved_league_id = league_id or _required_integer_environment("FPL_LEAGUE_ID")
            resolved_data_client: BaseStreamingDataClient[FPLData] = FPLDataClient(
                resolved_league_id,
                base_url=os.getenv("FPL_API_BASE_URL", DEFAULT_BASE_URL),
                requests_per_second=_float_environment(
                    "FPL_REQUESTS_PER_SECOND",
                    DEFAULT_REQUESTS_PER_SECOND,
                ),
            )
        else:
            resolved_data_client = data_client

        super().__init__(DATASOURCE_NAME, resolved_data_client)
        self.allowed_user_email = resolved_email
        self.batch_size = 100
        if isinstance(resolved_data_client, FPLDataClient):
            resolved_data_client.observability = self.observability

    def transform(self, data: Sequence[FPLData]) -> Sequence[DocumentDefinition]:
        """Map tagged FPL source records to matching Glean document types."""
        documents: list[DocumentDefinition] = []
        counts: Counter[str] = Counter()

        for item in data:
            kind = item["kind"]
            if kind == "player":
                document = self._player_document(cast(PlayerData, item))
            elif kind == "club":
                document = self._club_document(cast(ClubData, item))
            elif kind == "league":
                document = self._league_document(cast(LeagueData, item))
            elif kind == "manager_team":
                document = self._manager_team_document(cast(ManagerTeamData, item))
            elif kind == "manager_gameweek":
                document = self._manager_gameweek_document(cast(ManagerGameweekData, item))
            else:
                raise ValueError(f"Unsupported FPL record kind: {kind}")
            documents.append(document)
            counts[document.object_type or "unknown"] += 1

        logger.info(
            "FPL records transformed",
            extra={
                "operation": "transform_completed",
                "input_count": len(data),
                "output_count": len(documents),
                "object_type_counts": dict(sorted(counts.items())),
            },
        )
        return documents

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: ConnectorOptions | None = None,
    ) -> None:
        """Run a full crawl with explicit lifecycle observability."""
        if mode != IndexingMode.FULL:
            raise ValueError("The FPL connector supports full crawls only")

        self.observability.start_execution()
        try:
            logger.info(
                "Indexing sole permitted datasource user",
                extra={"operation": "permission_user_index_started", "user_count": 1},
            )
            PushUploader(
                datasource=self.name,
                observability=self.observability,
            ).index_user(
                DatasourceUserDefinition(
                    email=self.allowed_user_email,
                    name=self.allowed_user_email,
                ),
            )
            super().index_data(mode=mode, options=options)
        except Exception as error:
            self.observability.fail_execution(error)
            raise
        finally:
            self.observability.end_execution()

    def _player_document(self, player: PlayerData) -> DocumentDefinition:
        status = STATUS_LABELS.get(player["status"], player["status"])
        fixture_html = _fixture_list(player["fixtures"], "No upcoming fixtures are scheduled.")
        statistics = "".join(
            f"<dt>{_text(name.replace('_', ' ').title())}</dt><dd>{_text(value)}</dd>"
            for name, value in player["statistics"].items()
        )
        news = f"<p><strong>News:</strong> {_text(player['news'])}</p>" if player["news"] else ""
        body = _article(
            f"{player['name']} — {player['club']}",
            f"""
            <p><strong>Position:</strong> {_text(player["position"])} ·
            <strong>Price:</strong> £{player["price"]:.1f}m ·
            <strong>Status:</strong> {_text(status)}</p>
            {news}
            <h2>FPL snapshot</h2>
            <dl>
              <dt>Total points</dt><dd>{player["total_points"]}</dd>
              <dt>Points per game</dt><dd>{_text(player["points_per_game"])}</dd>
              <dt>Form</dt><dd>{_text(player["form"])}</dd>
              <dt>Selected by</dt><dd>{_text(player["selected_by_percent"])}%</dd>
            </dl>
            <h2>Upcoming club fixtures</h2>
            {fixture_html}
            <h2>Season statistics</h2>
            <dl>{statistics}</dl>
            """,
        )
        return self._document(
            document_id=str(player["id"]),
            object_type=PLAYER_OBJECT_TYPE,
            title=f"{player['name']} — {player['club']}",
            summary=(
                f"{player['position']} for {player['club']}; £{player['price']:.1f}m, "
                f"{player['total_points']} points, form {player['form']}."
            ),
            body=body,
            view_url=player["view_url"],
            updated_at=player["updated_at"],
            tags=["FPL", "Player", player["club"], player["position"], status],
        )

    def _club_document(self, club: ClubData) -> DocumentDefinition:
        player_rows = "".join(
            f"<tr><td>{_text(player['web_name'])}</td><td>{_text(player['position'])}</td></tr>"
            for player in club["players"]
        )
        strength = club["strength"] if club["strength"] is not None else "Not published"
        body = _article(
            club["name"],
            f"""
            <p><strong>Short name:</strong> {_text(club["short_name"])} ·
            <strong>Table position:</strong> {club["position"]} ·
            <strong>Points:</strong> {club["points"]}</p>
            <h2>Record and FPL strength</h2>
            <dl>
              <dt>Played</dt><dd>{club["played"]}</dd>
              <dt>Wins</dt><dd>{club["win"]}</dd>
              <dt>Draws</dt><dd>{club["draw"]}</dd>
              <dt>Losses</dt><dd>{club["loss"]}</dd>
              <dt>Overall strength</dt><dd>{_text(strength)}</dd>
              <dt>Home attack</dt><dd>{club["strength_attack_home"]}</dd>
              <dt>Away attack</dt><dd>{club["strength_attack_away"]}</dd>
              <dt>Home defence</dt><dd>{club["strength_defence_home"]}</dd>
              <dt>Away defence</dt><dd>{club["strength_defence_away"]}</dd>
            </dl>
            <h2>Upcoming fixtures</h2>
            {_fixture_list(club["upcoming_fixtures"], "No upcoming fixtures are scheduled.")}
            <h2>Recent results</h2>
            {_fixture_list(club["recent_fixtures"], "No completed fixtures yet.")}
            <h2>FPL players</h2>
            <table><thead><tr><th>Player</th><th>Position</th></tr></thead>
            <tbody>{player_rows}</tbody></table>
            """,
        )
        return self._document(
            document_id=str(club["id"]),
            object_type=CLUB_OBJECT_TYPE,
            title=club["name"],
            summary=(
                f"{club['name']} are {club['position']} in the table with "
                f"{club['points']} points and {len(club['players'])} FPL players."
            ),
            body=body,
            view_url=club["view_url"],
            updated_at=club["updated_at"],
            tags=["FPL", "Club", club["name"], club["short_name"]],
        )

    def _league_document(self, league: LeagueData) -> DocumentDefinition:
        standings_rows = "".join(
            "<tr>"
            f"<td>{standing['rank']}</td>"
            f"<td>{_text(standing['team_name'])}</td>"
            f"<td>{_text(standing['manager_name'])}</td>"
            f"<td>{standing['event_total']}</td>"
            f"<td>{standing['total']}</td>"
            "</tr>"
            for standing in sorted(league["standings"], key=lambda item: item["rank"])
        )
        scoring = "Classic" if league["scoring"] == "c" else league["scoring"]
        body = _article(
            league["name"],
            f"""
            <p><strong>Scoring:</strong> {_text(scoring)} ·
            <strong>Started:</strong> Gameweek {league["start_event"]} ·
            <strong>Managers:</strong> {len(league["standings"])}</p>
            <h2>Standings</h2>
            <table>
              <thead><tr><th>Rank</th><th>Team</th><th>Manager</th><th>GW</th><th>Total</th></tr></thead>
              <tbody>{standings_rows}</tbody>
            </table>
            """,
        )
        return self._document(
            document_id=str(league["id"]),
            object_type=LEAGUE_OBJECT_TYPE,
            title=f"{league['name']} — FPL standings",
            summary=(
                f"Classic FPL league with {len(league['standings'])} managers, "
                f"starting in gameweek {league['start_event']}."
            ),
            body=body,
            view_url=league["view_url"],
            updated_at=league["updated_at"],
            tags=["FPL", "League", league["name"]],
        )

    def _manager_team_document(self, manager: ManagerTeamData) -> DocumentDefinition:
        history_rows = "".join(
            "<tr>"
            f"<td>{row['event']}</td>"
            f"<td>{row['points']}</td>"
            f"<td>{row['total_points']}</td>"
            f"<td>{_text(_display_optional(row['overall_rank']))}</td>"
            f"<td>£{row['value'] / 10:.1f}m</td>"
            f"<td>{row['transfers']}</td>"
            f"<td>{row['transfer_cost']}</td>"
            f"<td>{row['bench_points']}</td>"
            "</tr>"
            for row in manager["history"]
        )
        chip_items = "".join(
            f"<li>{_text(chip['name'])} — Gameweek {chip['event']}</li>"
            for chip in manager["chips"]
        )
        prior_rows = "".join(
            "<tr>"
            f"<td>{_text(row['season_name'])}</td>"
            f"<td>{row['total_points']}</td>"
            f"<td>{row['rank']:,}</td>"
            "</tr>"
            for row in manager["prior_seasons"]
        )
        favourite = (
            f"<p><strong>Favourite club:</strong> {_text(manager['favourite_club'])}</p>"
            if manager["favourite_club"]
            else ""
        )
        body = _article(
            manager["team_name"],
            f"""
            <p><strong>Manager:</strong> {_text(manager["manager_name"])} ·
            <strong>League rank:</strong> {manager["rank"]} ·
            <strong>Gameweek points:</strong> {manager["event_total"]} ·
            <strong>Total points:</strong> {manager["total"]}</p>
            <p><strong>Overall rank:</strong> {_text(_display_optional(manager["overall_rank"]))}</p>
            {favourite}
            <h2>Current-season history</h2>
            <table>
              <thead><tr><th>GW</th><th>Points</th><th>Total</th><th>Overall rank</th>
              <th>Squad value</th><th>Transfers</th><th>Cost</th><th>Bench</th></tr></thead>
              <tbody>{history_rows}</tbody>
            </table>
            <h2>Chips</h2>
            {_optional_list(chip_items, "No chips used yet.")}
            <h2>Prior seasons</h2>
            {_optional_table(prior_rows, ("Season", "Points", "Rank"), "No prior-season history.")}
            """,
        )
        return self._document(
            document_id=str(manager["manager_id"]),
            object_type=MANAGER_TEAM_OBJECT_TYPE,
            title=f"{manager['team_name']} — {manager['manager_name']}",
            summary=(
                f"Rank {manager['rank']} in the league with {manager['total']} total "
                f"points; {manager['event_total']} in the latest gameweek."
            ),
            body=body,
            view_url=manager["view_url"],
            updated_at=manager["updated_at"],
            tags=["FPL", "Manager Team", manager["team_name"], manager["manager_name"]],
        )

    def _manager_gameweek_document(
        self,
        manager_gameweek: ManagerGameweekData,
    ) -> DocumentDefinition:
        starting_rows = _pick_rows(manager_gameweek["picks"][:11])
        bench_rows = _pick_rows(manager_gameweek["picks"][11:])
        substitutions = "".join(
            f"<li>{_text(sub['player_in'])} replaced {_text(sub['player_out'])}</li>"
            for sub in manager_gameweek["automatic_subs"]
        )
        chip = manager_gameweek["active_chip"] or "None"
        gameweek_status = (
            "Final"
            if manager_gameweek["is_finished"]
            else "Live/provisional until the gameweek finishes"
        )
        body = _article(
            f"{manager_gameweek['team_name']} — {manager_gameweek['event_name']}",
            f"""
            <p><strong>Manager:</strong> {_text(manager_gameweek["manager_name"])} ·
            <strong>Gameweek points:</strong> {manager_gameweek["points"]} ·
            <strong>Season total:</strong> {manager_gameweek["total_points"]} ·
            <strong>Overall rank:</strong>
            {_text(_display_optional(manager_gameweek["overall_rank"]))}</p>
            <p><strong>Status:</strong> {_text(gameweek_status)}</p>
            <p><strong>Active chip:</strong> {_text(chip)}</p>
            <h2>Starting XI</h2>
            {_pick_table(starting_rows)}
            <h2>Bench</h2>
            {_pick_table(bench_rows)}
            <h2>Automatic substitutions</h2>
            {_optional_list(substitutions, "No automatic substitutions.")}
            """,
        )
        return self._document(
            document_id=f"{manager_gameweek['manager_id']}:{manager_gameweek['event']}",
            object_type=MANAGER_GAMEWEEK_OBJECT_TYPE,
            title=(f"{manager_gameweek['team_name']} — {manager_gameweek['event_name']}"),
            summary=(
                f"{manager_gameweek['manager_name']} "
                f"{'scored' if manager_gameweek['is_finished'] else 'currently has'} "
                f"{manager_gameweek['points']} points in "
                f"{manager_gameweek['event_name']}."
            ),
            body=body,
            view_url=manager_gameweek["view_url"],
            updated_at=manager_gameweek["updated_at"],
            tags=[
                "FPL",
                "Manager Gameweek",
                manager_gameweek["event_name"],
                manager_gameweek["team_name"],
                manager_gameweek["manager_name"],
            ],
        )

    def _document(
        self,
        *,
        document_id: str,
        object_type: str,
        title: str,
        summary: str,
        body: str,
        view_url: str,
        updated_at: int,
        tags: list[str],
    ) -> DocumentDefinition:
        return DocumentDefinition(
            id=document_id,
            datasource=self.name,
            object_type=object_type,
            title=title,
            summary=ContentDefinition(mime_type="text/plain", text_content=summary),
            body=ContentDefinition(mime_type="text/html", text_content=body),
            view_url=view_url,
            permissions=DocumentPermissionsDefinition(
                allowed_users=[UserReferenceDefinition(email=self.allowed_user_email)],
                allow_anonymous_access=False,
                allow_all_datasource_users_access=False,
            ),
            updated_at=updated_at,
            tags=tags,
        )


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_integer_environment(name: str) -> int:
    raw = _required_environment(name)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _float_environment(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _article(title: str, content: str) -> str:
    return f"<article><h1>{_text(title)}</h1>{content}</article>"


def _text(value: Any) -> str:
    return escape(str(value), quote=True)


def _display_optional(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _fixture_list(fixtures: Sequence[FixtureSummary], empty_message: str) -> str:
    if not fixtures:
        return f"<p>{_text(empty_message)}</p>"
    items = []
    for fixture in fixtures:
        venue = "vs" if fixture["is_home"] else "at"
        kickoff = f" · {_text(fixture['kickoff_time'])}" if fixture["kickoff_time"] else ""
        score = f" · {_text(fixture['score'])}" if fixture["score"] else ""
        items.append(
            f"<li>{_text(fixture['event_name'])}: {venue} "
            f"{_text(fixture['opponent'])} · difficulty {fixture['difficulty']}"
            f"{kickoff}{score}</li>"
        )
    return f"<ul>{''.join(items)}</ul>"


def _optional_list(items: str, empty_message: str) -> str:
    return f"<ul>{items}</ul>" if items else f"<p>{_text(empty_message)}</p>"


def _optional_table(rows: str, headers: Sequence[str], empty_message: str) -> str:
    if not rows:
        return f"<p>{_text(empty_message)}</p>"
    heading = "".join(f"<th>{_text(header)}</th>" for header in headers)
    return f"<table><thead><tr>{heading}</tr></thead><tbody>{rows}</tbody></table>"


def _pick_rows(picks: Sequence[PickSummary]) -> str:
    rows = []
    for pick in picks:
        role = ""
        if pick["is_captain"]:
            role = "Captain"
        elif pick["is_vice_captain"]:
            role = "Vice-captain"
        elif pick["multiplier"] == 0:
            role = "Bench"
        rows.append(
            "<tr>"
            f"<td>{pick['squad_position']}</td>"
            f"<td>{_text(pick['player_name'])}</td>"
            f"<td>{_text(pick['club'])}</td>"
            f"<td>{_text(pick['position_name'])}</td>"
            f"<td>{_text(role)}</td>"
            f"<td>{pick['points']}</td>"
            f"<td>{pick['effective_points']}</td>"
            "</tr>"
        )
    return "".join(rows)


def _pick_table(rows: str) -> str:
    return (
        "<table><thead><tr><th>#</th><th>Player</th><th>Club</th>"
        "<th>Position</th><th>Role</th><th>Raw points</th><th>Counted points</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
