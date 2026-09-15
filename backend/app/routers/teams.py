"""
GET /api/teams/{team_id}

Hardcoded for now (US-02). `team_id` is accepted so the frontend can wire
up routing/links immediately; it's ignored until the real DB lookup goes in.
"""

from fastapi import APIRouter

from app.schemas import RatingPoint, RecentResult, TeamDetailResponse

router = APIRouter(prefix="/api/teams", tags=["teams"])

_MOCK_TEAM = TeamDetailResponse(
    team="Alabama",
    conference="SEC",
    rank=2,
    wins=3,
    losses=0,
    power_score=97.1,
    recent_results=[
        RecentResult(week=1, opponent="Florida State", result="W 24-17"),
        RecentResult(week=2, opponent="South Florida", result="W 45-14"),
        RecentResult(week=3, opponent="Wisconsin", result="W 31-10"),
    ],
    rating_trend=[
        RatingPoint(week=1, rating=93.5),
        RatingPoint(week=2, rating=95.0),
        RatingPoint(week=3, rating=97.1),
    ],
)


@router.get("/{team_id}", response_model=TeamDetailResponse)
def get_team_detail(team_id: int):
    return _MOCK_TEAM
