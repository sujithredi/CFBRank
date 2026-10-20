"""
GET /api/teams/{team_id}

Team profile for the detail panel (US-02): current rank and rating, recent
results, and the week-by-week rating trend, all read from the database.

`team_id` is the internal `teams.id` primary key -- the same value the
rankings endpoint returns as `team_id`. It is not the CFBD id and not the
team's current rank (ranks change every week).
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Conference, Game, PowerRating, Team
from app.schemas import RatingPoint, RecentResult, ScheduleGame, TeamDetailResponse

router = APIRouter(prefix="/api/teams", tags=["teams"])

RECENT_RESULTS_LIMIT = 5

# Upper bound keeps absurdly large ids from overflowing the database's integer
# type (SQLite raises OverflowError, which would surface as a 500).
MAX_TEAM_ID = 2_147_483_647


def _outcome(team_points: int, opponent_points: int) -> str:
    if team_points > opponent_points:
        return "W"
    if team_points < opponent_points:
        return "L"
    return "T"


def _format_result(game: Game, team_id: int) -> RecentResult:
    """One finished game from `team_id`'s point of view, e.g. 'W 34-17'."""
    is_home = game.home_team_id == team_id
    team_points = game.home_points if is_home else game.away_points
    opponent_points = game.away_points if is_home else game.home_points
    opponent = game.away_team if is_home else game.home_team

    return RecentResult(
        week=game.week,
        opponent=opponent.school,
        result=f"{_outcome(team_points, opponent_points)} {team_points}-{opponent_points}",
    )


def _format_schedule_game(game: Game, team_id: int) -> ScheduleGame:
    """One game, finished or upcoming, from `team_id`'s point of view."""
    is_home = game.home_team_id == team_id
    opponent = game.away_team if is_home else game.home_team
    finished = game.completed and game.home_points is not None and game.away_points is not None

    if game.neutral_site:
        location = "neutral"
    else:
        location = "home" if is_home else "away"

    outcome = score = None
    if finished:
        team_points = game.home_points if is_home else game.away_points
        opponent_points = game.away_points if is_home else game.home_points
        outcome = _outcome(team_points, opponent_points)
        score = f"{team_points}-{opponent_points}"

    # SQLite drops the timezone; CFBD start times are UTC, so say so, which lets the
    # browser show the date in the viewer's own timezone.
    start_date = game.start_date
    if start_date is not None and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    return ScheduleGame(
        week=game.week,
        opponent=opponent.school,
        opponent_logo_url=opponent.logo_url,
        location=location,
        completed=finished,
        outcome=outcome,
        score=score,
        start_date=start_date,
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

    # The whole season, in date order; games with no date yet go last.
    season_games = (
        db.query(Game)
        .options(joinedload(Game.home_team), joinedload(Game.away_team))
        .filter(
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            Game.season == latest.season,
        )
        .all()
    )
    season_games.sort(key=lambda g: (g.start_date is None, g.start_date or datetime.min, g.week, g.id))

    return TeamDetailResponse(
        team=school,
        conference=conference_name or "Independent",
        rank=latest.rank,
        wins=latest.wins,
        losses=latest.losses,
        power_score=round(latest.rating, 2),
        offense_rating=None if latest.offense_rating is None else round(latest.offense_rating, 2),
        defense_rating=None if latest.defense_rating is None else round(latest.defense_rating, 2),
        recent_results=[_format_result(game, team_id) for game in recent_games],
        schedule=[_format_schedule_game(game, team_id) for game in season_games],
        rating_trend=[RatingPoint(week=week, rating=round(rating, 2)) for week, rating in trend_rows],
    )
