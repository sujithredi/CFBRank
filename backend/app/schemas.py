"""
Pydantic response shapes for the three MVP endpoints.

These are what the frontend will actually be built against, so they're
defined here up front and wired to hardcoded data in routers/ for now.
Swapping the hardcoded data for real DB queries later shouldn't require
changing these shapes (or the frontend).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---- Rankings -------------------------------------------------------------

class RankingEntry(BaseModel):
    rank: int
    # teams.id -- what /api/teams/{team_id} expects. None only for the hardcoded
    # fallback rows, which don't correspond to real database teams.
    team_id: int | None = None
    team: str
    # teams.logo_url from the database. None for the hardcoded fallback rows
    # and for any team without a logo on file.
    logo_url: str | None = None
    conference: str
    # The conference's classification from the database ("fbs" / "fcs"). None for the
    # hardcoded fallback rows and for teams without a conference.
    conference_classification: str | None = None
    wins: int
    losses: int
    # Overall rating (offense + defense) -- the number the ranking sorts on.
    power_score: float
    # Points per game above/below an average team, 0 = league average, positive
    # = better. None for the hardcoded fallback rows and for snapshots computed
    # before offense/defense ratings existed.
    offense_rating: float | None = None
    defense_rating: float | None = None
    # Rest-of-season Monte Carlo projection (scripts/simulate_season.py). All None
    # until it has been run for this snapshot, and for the fallback rows.
    # projected_wins/losses are full-season averages (games already played
    # included). bowl_pct and undefeated_pct are 0-100; bowl_pct is also None
    # for FCS teams, which don't play in bowls.
    projected_wins: float | None = None
    projected_losses: float | None = None
    bowl_pct: float | None = None
    undefeated_pct: float | None = None
    # Conference championship game, 0-100: chance of playing in it, and of winning
    # it. None for teams in conferences without a title game (FCS, independents).
    # The title game is never part of projected_wins/projected_losses.
    title_game_pct: float | None = None
    conf_champ_pct: float | None = None
    # College Football Playoff, 0-100: chance of being selected for the 12-team field
    # (conference champions + at-large picks from app/playoff.py). None for FCS teams.
    playoff_pct: float | None = None
    # The playoff games (app/playoff_bracket.py), each 0-100 out of every simulated season, so a
    # team that misses the field is a 0 here. Nested: bye <= quarterfinal and
    # champion <= final <= semifinal <= quarterfinal <= playoff_pct. None for FCS teams.
    cfp_bye_pct: float | None = None  # a top-4 seed, with a first-round bye
    cfp_quarterfinal_pct: float | None = None  # plays in the quarterfinals (bye or first-round win)
    cfp_semifinal_pct: float | None = None
    cfp_final_pct: float | None = None  # plays in the national championship game
    cfp_champion_pct: float | None = None  # wins it


class RankingsResponse(BaseModel):
    season: int
    week: int
    last_updated: datetime
    rankings: list[RankingEntry]
    # How many simulated seasons the projection fields are based on; None if
    # there is no projection for this snapshot.
    simulations: int | None = None


# ---- Team detail ------------------------------------------------------------

class RecentResult(BaseModel):
    week: int
    opponent: str
    result: str  # e.g. "W 34-17"


class ScheduleGame(BaseModel):
    """One game on the team's season schedule, from that team's point of view."""

    week: int
    opponent: str
    opponent_logo_url: str | None = None
    # "away" is shown as "@"; "home" and "neutral" are shown as "vs".
    location: Literal["home", "away", "neutral"]
    completed: bool
    # Only set once the game is finished: "W" / "L" / "T" and the score with this
    # team's points first, e.g. "66-3". None for upcoming games.
    outcome: Literal["W", "L", "T"] | None = None
    score: str | None = None
    # Kickoff, in UTC. None when the game has no date on file yet.
    start_date: datetime | None = None


class RatingPoint(BaseModel):
    week: int
    rating: float


class TeamDetailResponse(BaseModel):
    team: str
    conference: str
    rank: int
    wins: int
    losses: int
    power_score: float
    offense_rating: float | None = None
    defense_rating: float | None = None
    recent_results: list[RecentResult]
    # Every game this season (finished and upcoming), in date order.
    schedule: list[ScheduleGame] = []
    rating_trend: list[RatingPoint]


# ---- Weekly odds ------------------------------------------------------------

class GameOdds(BaseModel):
    game_id: int
    start_date: datetime
    home_team: str
    away_team: str
    home_logo_url: str | None = None
    away_logo_url: str | None = None
    # The model's numbers are averages over `WeeklyOddsResponse.num_simulations` simulated games
    # (app/routers/odds.py): the points each team scores, the home team's margin (home minus away,
    # so it equals model_home_points - model_away_points) and the combined total.
    model_home_points: float
    model_away_points: float
    model_predicted_margin: float
    model_total: float
    # The share of the simulations the home team won, 0-1; the away team's is 1 minus this.
    model_home_win_prob: float
    market_spread: float | None
    market_home_moneyline: int | None
    market_away_moneyline: int | None
    delta: float | None


class WeeklyOddsResponse(BaseModel):
    season: int
    week: int
    # How many times each game was simulated to get the model numbers.
    num_simulations: int
    games: list[GameOdds]


# ---- Matchup simulation -----------------------------------------------------

# Where the game is played. "team_a_home" / "team_b_home" give that team the
# home-field edge (app.ranking.DEFAULT_HOME_FIELD_ADVANTAGE); "neutral" gives nobody one.
MatchupLocation = Literal["neutral", "team_a_home", "team_b_home"]

# Upper bound on games per request, so one call can't tie up the server.
MAX_SIMULATED_GAMES = 1000


class MatchupRequest(BaseModel):
    # teams.id values -- the same `team_id` the rankings endpoint returns.
    team_a_id: int = Field(ge=1, le=2_147_483_647)
    team_b_id: int = Field(ge=1, le=2_147_483_647)
    location: MatchupLocation = "neutral"
    # How many independent games to simulate between the two teams.
    num_games: int = Field(default=1, ge=1, le=MAX_SIMULATED_GAMES)


class MatchupTeamResult(BaseModel):
    team_id: int
    team: str
    logo_url: str | None = None
    offense_rating: float
    defense_rating: float
    # Points the model expects this team to score against this opponent, including
    # the home-field adjustment when `location` isn't neutral.
    expected_points: float
    # The first simulated game's final score (the only game when num_games is 1).
    # Every game is in `games` on the response.
    score: int


class MatchupGame(BaseModel):
    score_a: int
    score_b: int
    winner_team_id: int
    overtime: bool


class MatchupSeriesSummary(BaseModel):
    """Totals across all `num_games` simulated games."""

    team_a_wins: int
    team_b_wins: int
    # 0-100.
    team_a_win_pct: float
    team_b_win_pct: float
    avg_score_a: float
    avg_score_b: float
    overtime_games: int


class MatchupSimulationResponse(BaseModel):
    season: int
    week: int
    location: MatchupLocation
    num_games: int
    team_a: MatchupTeamResult
    team_b: MatchupTeamResult
    # The first game, kept at the top level so a single-game caller doesn't need `games`.
    winner_team_id: int
    overtime: bool
    # Every simulated game, in order (length == num_games), and the totals across them.
    games: list[MatchupGame]
    summary: MatchupSeriesSummary
