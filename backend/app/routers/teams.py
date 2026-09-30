"""
GET /api/teams/{team_id}

Team profile for the detail panel (US-02): current rank and rating, recent
results, and the week-by-week rating trend, all read from the database.

`team_id` is the internal `teams.id` primary key -- the same value the
rankings endpoint returns as `team_id`. It is not the CFBD id and not the
team's current rank (ranks change every week).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Conference, Game, PowerRating, Team
from app.schemas import RatingPoint, RecentResult, TeamDetailResponse

router = APIRouter(prefix="/api/teams", tags=["teams"])

RECENT_RESULTS_LIMIT = 5

# Upper bound keeps absurdly large ids from overflowing the database's integer
# type (SQLite raises OverflowError, which would surface as a 500).
MAX_TEAM_ID = 2_147_483_647


def _format_result(game: Game, team_id: int) -> RecentResult:
    """One finished game from `team_id`'s point of view, e.g. 'W 34-17'."""
    is_home = game.home_team_id == team_id
    team_points = game.home_points if is_home else game.away_points
    opponent_points = game.away_points if is_home else game.home_points
    opponent = game.away_team if is_home else game.home_team

    if team_points > opponent_points:
        outcome = "W"
    elif team_points < opponent_points:
        outcome = "L"
    else:
        outcome = "T"

    return RecentResult(
        week=game.week,
        opponent=opponent.school,
        result=f"{outcome} {team_points}-{opponent_points}",
    )


@router.get("/{team_id}", response_model=TeamDetailResponse)
def get_team_detail(
    team_id: Annotated[int, Path(ge=1, le=MAX_TEAM_ID)],
    db: Session = Depends(get_db),
):
    # Join on Conference.id, the same way app/rankings.py does: seed_teams.py
    # stores conferences.id in teams.conference_id, so the `Team.conference`
    # relationship (whose FK points at conferences.cfbd_id) can't be trusted here.
    team_row = (
        db.query(Team.school, Conference.name)
        .outerjoin(Conference, Team.conference_id == Conference.id)
        .filter(Team.id == team_id)
        .first()
    )
    if team_row is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    school, conference_name = team_row

    latest = (
        db.query(PowerRating)
        .filter(PowerRating.team_id == team_id)
        .order_by(PowerRating.season.desc(), PowerRating.week.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(status_code=404, detail=f"No power rating on file yet for {school}")

    trend_rows = (
        db.query(PowerRating.week, PowerRating.rating)
        .filter(PowerRating.team_id == team_id, PowerRating.season == latest.season)
        .order_by(PowerRating.week.asc())
        .all()
    )

    # Newest N finished games, then flipped so they read oldest -> newest.
    recent_games = (
        db.query(Game)
        .options(joinedload(Game.home_team), joinedload(Game.away_team))
        .filter(
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            Game.season == latest.season,
            Game.completed.is_(True),
            Game.home_points.isnot(None),
            Game.away_points.isnot(None),
        )
        .order_by(Game.week.desc(), Game.start_date.desc(), Game.id.desc())
        .limit(RECENT_RESULTS_LIMIT)
        .all()
    )
    recent_games.reverse()

    return TeamDetailResponse(
        team=school,
        conference=conference_name or "Independent",
        rank=latest.rank,
        wins=latest.wins,
        losses=latest.losses,
        power_score=round(latest.rating, 2),
        recent_results=[_format_result(game, team_id) for game in recent_games],
        rating_trend=[RatingPoint(week=week, rating=round(rating, 2)) for week, rating in trend_rows],
    )
