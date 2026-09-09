"""Typed source records emitted by the FPL data client."""

from typing import Any, Literal, TypedDict, Union


class FixtureSummary(TypedDict):
    """Fixture information rendered on player and club documents."""

    event: int | None
    event_name: str
    opponent: str
    kickoff_time: str | None
    difficulty: int
    is_home: bool
    finished: bool
    score: str | None


class PlayerSummary(TypedDict):
    """Compact player identity used in club and squad records."""

    id: int
    name: str
    web_name: str
    club: str
    position: str


class StandingSummary(TypedDict):
    """One row in the selected league standings."""

    manager_id: int
    manager_name: str
    team_name: str
    rank: int
    last_rank: int
    event_total: int
    total: int


class ManagerHistorySummary(TypedDict):
    """One gameweek from a manager's season history."""

    event: int
    points: int
    total_points: int
    rank: int | None
    overall_rank: int | None
    bank: int
    value: int
    transfers: int
    transfer_cost: int
    bench_points: int


class ChipSummary(TypedDict):
    """A chip used by a manager."""

    name: str
    event: int


class PriorSeasonSummary(TypedDict):
    """A manager's previous-season result."""

    season_name: str
    total_points: int
    rank: int


class PickSummary(TypedDict):
    """One selected player in a finalized manager gameweek."""

    player_id: int
    player_name: str
    club: str
    position_name: str
    squad_position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool
    points: int
    effective_points: int


class AutomaticSubSummary(TypedDict):
    """An automatic substitution in a finalized manager gameweek."""

    player_in: str
    player_out: str


class PlayerData(TypedDict):
    """Current-season FPL player document source."""

    kind: Literal["player"]
    id: int
    name: str
    web_name: str
    club: str
    position: str
    price: float
    status: str
    news: str
    selected_by_percent: str
    form: str
    points_per_game: str
    total_points: int
    statistics: dict[str, Any]
    fixtures: list[FixtureSummary]
    view_url: str
    updated_at: int


class ClubData(TypedDict):
    """Premier League club document source."""

    kind: Literal["club"]
    id: int
    name: str
    short_name: str
    position: int
    played: int
    win: int
    draw: int
    loss: int
    points: int
    strength: int | None
    strength_attack_home: int
    strength_attack_away: int
    strength_defence_home: int
    strength_defence_away: int
    players: list[PlayerSummary]
    recent_fixtures: list[FixtureSummary]
    upcoming_fixtures: list[FixtureSummary]
    view_url: str
    updated_at: int


class LeagueData(TypedDict):
    """Selected FPL league overview document source."""

    kind: Literal["league"]
    id: int
    name: str
    scoring: str
    start_event: int
    standings: list[StandingSummary]
    view_url: str
    updated_at: int


class ManagerTeamData(TypedDict):
    """One manager team's season overview document source."""

    kind: Literal["manager_team"]
    manager_id: int
    manager_name: str
    team_name: str
    rank: int
    last_rank: int
    event_total: int
    total: int
    overall_rank: int | None
    favourite_club: str | None
    history: list[ManagerHistorySummary]
    chips: list[ChipSummary]
    prior_seasons: list[PriorSeasonSummary]
    view_url: str
    updated_at: int


class ManagerGameweekData(TypedDict):
    """One public manager squad after its gameweek deadline."""

    kind: Literal["manager_gameweek"]
    manager_id: int
    manager_name: str
    team_name: str
    event: int
    event_name: str
    is_finished: bool
    points: int
    total_points: int
    overall_rank: int | None
    active_chip: str | None
    picks: list[PickSummary]
    automatic_subs: list[AutomaticSubSummary]
    view_url: str
    updated_at: int


FPLData = Union[PlayerData, ClubData, LeagueData, ManagerTeamData, ManagerGameweekData]
