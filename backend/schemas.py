"""
Pydantic response shapes for the three MVP endpoints.

These are what the frontend will actually be built against, so they're
defined here up front and wired to hardcoded data in routers/ for now.
Swapping the hardcoded data for real DB queries later shouldn't require
changing these shapes (or the frontend).
"""

from datetime import datetime

from pydantic import BaseModel


# ---- Rankings -------------------------------------------------------------

class RankingEntry(BaseModel):
    rank: int
    team: str
    conference: str
    wins: int
    losses: int
    power_score: float


class RankingsResponse(BaseModel):
    season: int
    week: int
    last_updated: datetime
    rankings: list[RankingEntry]


# ---- Team detail ------------------------------------------------------------

class RecentResult(BaseModel):
    week: int
    opponent: str
    result: str  # e.g. "W 34-17"


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
    recent_results: list[RecentResult]
    rating_trend: list[RatingPoint]


# ---- Weekly odds ------------------------------------------------------------

class GameOdds(BaseModel):
    game_id: int
    start_date: datetime
    home_team: str
    away_team: str
    model_predicted_margin: float       # points; positive favors home, negative favors away
    model_home_win_prob: float          # 0-1
    market_spread: float | None         # negative favors home, per convention
    market_home_moneyline: int | None
    market_away_moneyline: int | None
    delta: float | None                 # model prob minus market-implied prob


class WeeklyOddsResponse(BaseModel):
    season: int
    week: int
    games: list[GameOdds]
