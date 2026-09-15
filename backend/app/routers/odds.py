"""
GET /api/odds/weekly

Hardcoded for now (US-03: model win % next to market line, with a delta).
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas import GameOdds, WeeklyOddsResponse

router = APIRouter(prefix="/api/odds", tags=["odds"])

_MOCK_ODDS = WeeklyOddsResponse(
    season=2026,
    week=3,
    games=[
        GameOdds(
            game_id=401520123,
            start_date=datetime.now(timezone.utc),
            home_team="Alabama",
            away_team="Wisconsin",
            model_home_win_prob=0.88,
            market_spread=-13.5,
            market_home_moneyline=-650,
            market_away_moneyline=480,
            delta=0.04,
        ),
        GameOdds(
            game_id=401520124,
            start_date=datetime.now(timezone.utc),
            home_team="Georgia",
            away_team="Kentucky",
            model_home_win_prob=0.81,
            market_spread=-10.0,
            market_home_moneyline=-420,
            market_away_moneyline=340,
            delta=-0.03,
        ),
    ],
)


@router.get("/weekly", response_model=WeeklyOddsResponse)
def get_weekly_odds():
    return _MOCK_ODDS
