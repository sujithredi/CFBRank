"""
GET /api/rankings

Hardcoded for now so the frontend has a real, stable shape to build
against (US-01). Swap the body of `get_rankings` for a DB query once the
ranking job is writing PowerRating rows -- the response_model doesn't
need to change.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas import RankingEntry, RankingsResponse

router = APIRouter(prefix="/api/rankings", tags=["rankings"])

_MOCK_RANKINGS = RankingsResponse(
    season=2026,
    week=3,
    last_updated=datetime.now(timezone.utc),
    rankings=[
        RankingEntry(rank=1, team="Ohio State", conference="Big Ten", wins=3, losses=0, power_score=98.4),
        RankingEntry(rank=2, team="Alabama", conference="SEC", wins=3, losses=0, power_score=97.1),
        RankingEntry(rank=3, team="Georgia", conference="SEC", wins=2, losses=1, power_score=95.8),
        RankingEntry(rank=4, team="Oregon", conference="Big Ten", wins=3, losses=0, power_score=95.2),
        RankingEntry(rank=5, team="Texas", conference="SEC", wins=2, losses=1, power_score=94.0),
    ],
)


@router.get("", response_model=RankingsResponse)
def get_rankings():
    return _MOCK_RANKINGS
