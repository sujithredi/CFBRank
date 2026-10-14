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
from app.models import Conference, PowerRating, SeasonProjection, Team
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
            PowerRating.offense_rating,
            PowerRating.defense_rating,
            Conference.name,
            Team.id,
            Team.logo_url,
            SeasonProjection.avg_wins,
            SeasonProjection.avg_losses,
            SeasonProjection.bowl_pct,
            SeasonProjection.undefeated_pct,
            SeasonProjection.title_game_pct,
            SeasonProjection.conf_champ_pct,
            SeasonProjection.playoff_pct,
            SeasonProjection.cfp_bye_pct,
            SeasonProjection.cfp_quarterfinal_pct,
            SeasonProjection.cfp_semifinal_pct,
            SeasonProjection.cfp_final_pct,
            SeasonProjection.cfp_champion_pct,
        )
        .join(Team, PowerRating.team_id == Team.id)
        .outerjoin(Conference, Team.conference_id == Conference.id)
        # Projections belong to a specific ratings snapshot, so an older week
        # (?week=3) simply has none rather than showing today's numbers.
        .outerjoin(
            SeasonProjection,
            (SeasonProjection.team_id == PowerRating.team_id)
            & (SeasonProjection.season == PowerRating.season)
            & (SeasonProjection.week == PowerRating.week),
        )
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

    simulations = (
        db.query(func.max(SeasonProjection.n_simulations))
        .filter(SeasonProjection.season == season, SeasonProjection.week == week)
        .scalar()
    )

    def rounded(value: float | None, digits: int = 2) -> float | None:
        return None if value is None else round(value, digits)

    rankings = [
        RankingEntry(
            rank=rank,
            team_id=team_id,
            team=school,
            logo_url=logo_url,
            conference=conference_name or "Independent",
            wins=wins,
            losses=losses,
            power_score=round(rating, 2),
            offense_rating=rounded(offense),
            defense_rating=rounded(defense),
            projected_wins=rounded(proj_wins),
            projected_losses=rounded(proj_losses),
            bowl_pct=rounded(bowl_pct),
            undefeated_pct=rounded(undefeated_pct),
            title_game_pct=rounded(title_game_pct),
            conf_champ_pct=rounded(conf_champ_pct),
            playoff_pct=rounded(playoff_pct),
            cfp_bye_pct=rounded(cfp_bye_pct),
            cfp_quarterfinal_pct=rounded(cfp_quarterfinal_pct),
            cfp_semifinal_pct=rounded(cfp_semifinal_pct),
            cfp_final_pct=rounded(cfp_final_pct),
            cfp_champion_pct=rounded(cfp_champion_pct),
        )
        for (
            rank, school, wins, losses, rating, offense, defense, conference_name, team_id, logo_url,
            proj_wins, proj_losses, bowl_pct, undefeated_pct, title_game_pct, conf_champ_pct, playoff_pct,
            cfp_bye_pct, cfp_quarterfinal_pct, cfp_semifinal_pct, cfp_final_pct, cfp_champion_pct,
        ) in rows
    ]

    return RankingsResponse(
        season=season, week=week, last_updated=last_updated, rankings=rankings, simulations=simulations
    )
