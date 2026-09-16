"""
GET /api/rankings

Reads the latest PowerRating snapshot written by
scripts/compute_rankings.py. Falls back to a small hardcoded response if
that job hasn't been run yet (e.g. a fresh clone with no games ingested),
so the frontend never gets a 500/empty page while the pipeline is being
set up (US-01).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conference, PowerRating, Team
from app.schemas import RankingEntry, RankingsResponse

router = APIRouter(prefix="/api/rankings", tags=["rankings"])

_FALLBACK_RANKINGS = RankingsResponse(
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


def _resolve_season_week(db: Session, season: int | None, week: int | None) -> tuple[int, int] | None:
    """Fill in whichever of (season, week) is missing from the latest snapshot on file."""
    if season is not None and week is not None:
        return season, week

    latest_query = db.query(PowerRating.season, PowerRating.week)
    if season is not None:
        latest_query = latest_query.filter(PowerRating.season == season)
    latest = latest_query.order_by(PowerRating.season.desc(), PowerRating.week.desc()).first()
    if latest is None:
        return None
    return season if season is not None else latest[0], week if week is not None else latest[1]


@router.get("", response_model=RankingsResponse)
def get_rankings(season: int | None = None, week: int | None = None, db: Session = Depends(get_db)):
    resolved = _resolve_season_week(db, season, week)
    if resolved is None:
        return _FALLBACK_RANKINGS
    season, week = resolved

    rows = (
        db.query(
            PowerRating.rank,
            Team.school,
            PowerRating.wins,
            PowerRating.losses,
            PowerRating.rating,
            Conference.name,
        )
        .join(Team, PowerRating.team_id == Team.id)
        .outerjoin(Conference, Team.conference_id == Conference.id)
        .filter(PowerRating.season == season, PowerRating.week == week)
        .order_by(PowerRating.rank.asc())
        .all()
    )
    if not rows:
        return _FALLBACK_RANKINGS

    last_updated = (
        db.query(func.max(PowerRating.computed_at))
        .filter(PowerRating.season == season, PowerRating.week == week)
        .scalar()
        or datetime.now(timezone.utc)
    )

    rankings = [
        RankingEntry(
            rank=rank,
            team=school,
            conference=conference_name or "Independent",
            wins=wins,
            losses=losses,
            power_score=round(rating, 2),
        )
        for rank, school, wins, losses, rating, conference_name in rows
    ]

    return RankingsResponse(season=season, week=week, last_updated=last_updated, rankings=rankings)
