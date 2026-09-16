"""
Standalone script: turn completed games already in the database (via
scripts/ingest_games.py) into power ratings, and write them to the
power_ratings table as a weekly snapshot.

This is the "Python power-rating calculation module, run on a schedule"
from the proposal (section 7) -- it reads Game rows, not the API directly,
so it always runs against whatever ingest_games.py has most recently
pulled down.

Usage (run from backend/):
    python -m scripts.compute_rankings --year 2026
    python -m scripts.compute_rankings --year 2026 --through-week 5
    python -m scripts.compute_rankings --year 2026 --season-type postseason

--through-week limits the model to games up through that week, e.g. to
reproduce what the rankings looked like at a given point in the season.
Omit it to use every completed game on file for that season/season-type.

Requires games to already be ingested (see scripts/ingest_games.py) --
this script does not call the CFBD API itself.
"""

import argparse
import os
import sys
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session, aliased

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Game, PowerRating, Team  # noqa: E402
from app.ranking import compute_power_ratings, record_from_games  # noqa: E402


def load_games_frame(db: Session, year: int, season_type: str, through_week: int | None) -> pd.DataFrame:
    """
    One row per completed game, home team as `team`, in the shape
    app.ranking.compute_power_ratings expects. Location is 1 unless the
    game was at a neutral site (0) -- the model derives the away
    perspective itself, so there's no -1 case to set here.
    """
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)

    query = (
        db.query(
            HomeTeam.school.label("team"),
            AwayTeam.school.label("opponent"),
            Game.home_points.label("team_score"),
            Game.away_points.label("opponent_score"),
            Game.neutral_site,
            Game.week,
        )
        .join(HomeTeam, Game.home_team_id == HomeTeam.id)
        .join(AwayTeam, Game.away_team_id == AwayTeam.id)
        .filter(
            Game.season == year,
            Game.season_type == season_type,
            Game.completed.is_(True),
            Game.home_points.isnot(None),
            Game.away_points.isnot(None),
        )
    )
    if through_week is not None:
        query = query.filter(Game.week <= through_week)

    rows = query.all()
    if not rows:
        return pd.DataFrame(columns=["team", "opponent", "team_score", "opponent_score", "margin", "Location", "week"])

    games = pd.DataFrame(rows, columns=["team", "opponent", "team_score", "opponent_score", "neutral_site", "week"])
    games["margin"] = games["team_score"] - games["opponent_score"]
    games["Location"] = games["neutral_site"].apply(lambda neutral: 0 if neutral else 1)
    return games.drop(columns=["neutral_site"])


def write_ratings(db: Session, ratings: pd.DataFrame, records: pd.DataFrame, year: int, week: int) -> int:
    merged = ratings.merge(records, on="team", how="left")
    merged[["wins", "losses"]] = merged[["wins", "losses"]].fillna(0).astype(int)

    written = 0
    unmatched: list[str] = []
    for row in merged.itertuples(index=False):
        team = db.query(Team).filter_by(school=row.team).first()
        if team is None:
            unmatched.append(row.team)
            continue

        power_rating = (
            db.query(PowerRating).filter_by(team_id=team.id, season=year, week=week).first()
        )
        if power_rating is None:
            power_rating = PowerRating(team_id=team.id, season=year, week=week)
            db.add(power_rating)

        power_rating.rating = float(row.rating)
        power_rating.rank = int(row.rank)
        power_rating.wins = int(row.wins)
        power_rating.losses = int(row.losses)
        power_rating.computed_at = datetime.utcnow()
        written += 1

    if unmatched:
        print(
            f"  warning: {len(unmatched)} team name(s) from the ranking model didn't match a "
            f"Team row (school name mismatch?): {sorted(set(unmatched))[:10]}"
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute power ratings from ingested games")
    parser.add_argument("--year", type=int, required=True, help="Season year, e.g. 2026")
    parser.add_argument(
        "--through-week", type=int, default=None, help="Only use games up through this week (default: all)"
    )
    parser.add_argument(
        "--season-type", default="regular", choices=["regular", "postseason"], help="Default: regular"
    )
    parser.add_argument("--top", type=int, default=25, help="How many teams to print (default: 25)")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        games = load_games_frame(db, args.year, args.season_type, args.through_week)
        print(f"Loaded {len(games)} completed {args.season_type} game(s) for {args.year}"
              + (f" through week {args.through_week}" if args.through_week else "") + ".")

        if games.empty:
            print("No completed games on file yet -- run scripts.ingest_games first.")
            return

        ratings = compute_power_ratings(games)
        records = record_from_games(games)
        snapshot_week = args.through_week if args.through_week is not None else int(games["week"].max())

        written = write_ratings(db, ratings, records, args.year, snapshot_week)
        db.commit()

        print(f"\nWrote {written} PowerRating row(s) for {args.year} week {snapshot_week}.\n")
        print(f"Top {min(args.top, len(ratings))}:")
        preview = ratings.merge(records, on="team", how="left").fillna(0)
        for row in preview.head(args.top).itertuples(index=False):
            print(f"  {row.rank:>3}. {row.team:<25} rating={row.rating:7.2f}  ({int(row.wins)}-{int(row.losses)})")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
