"""
Standalone script: pull games from the CollegeFootballData API and upsert
them into the database.

Usage (run from backend/):
    python -m scripts.ingest_games --year 2026
    python -m scripts.ingest_games --year 2026 --week 3
    python -m scripts.ingest_games --year 2026 --season-type postseason

Requires CFBD_API_KEY to be set (backend/.env, same as the FastAPI app).

Teams are matched against what's already in the database (seeded via
scripts/seed_teams.py) by CFBD id. A game is only added/updated if BOTH
its home and away team already exist there -- this script never creates
a Team row on its own. Games involving a team that isn't seeded yet are
skipped and printed to stdout, with a summary count at the end.

Note on field names: this targets CFBD's commonly-documented /games schema
(homeId/homeTeam/homePoints, awayId/awayTeam/awayPoints, startDate, etc.).
CFBD's API has multiple versions in the wild -- before relying on this for
real ingestion, hit the endpoint once (e.g. via /docs on api.collegefootballdata.com
or a quick curl) and confirm the field names below match what your key
actually returns, since this sandbox has no network path to verify live.
"""

import argparse
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Game, Team  # noqa: E402

load_dotenv()

CFBD_BASE_URL = "https://api.collegefootballdata.com"


def fetch_games(year: int, season_type: str, week: int | None) -> list[dict]:
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        raise RuntimeError("CFBD_API_KEY is not set (check backend/.env)")

    params = {"year": year, "seasonType": season_type}
    if week is not None:
        params["week"] = week

    resp = requests.get(
        f"{CFBD_BASE_URL}/games",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_existing_team(db: Session, cfbd_id: int | None) -> Team | None:
    """
    Look up a team already in the database by CFBD id. Returns None if it
    isn't there (or no id was given) -- ingestion never creates a Team row
    on the fly. Run scripts/seed_teams.py (and seed_conferences.py) first;
    any game involving a team missing from that seed is skipped rather
    than silently adding a bare-bones Team row for it.
    """
    if cfbd_id is None:
        return None
    return db.query(Team).filter_by(cfbd_id=cfbd_id).first()


def parse_start_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def upsert_game(db: Session, payload: dict, season: int, season_type: str) -> str:
    """Returns 'added', 'updated', or 'skipped' (unknown team on either side)."""
    home_id, home_school = payload.get("homeId"), payload.get("homeTeam")
    away_id, away_school = payload.get("awayId"), payload.get("awayTeam")

    home_team = get_existing_team(db, home_id)
    away_team = get_existing_team(db, away_id)

    if home_team is None or away_team is None:
        missing = []
        if home_team is None:
            missing.append(f"home={home_school!r} (cfbd_id={home_id})")
        if away_team is None:
            missing.append(f"away={away_school!r} (cfbd_id={away_id})")
        print(f"  skipping game {payload.get('id')}: not in database -- {', '.join(missing)}")
        return "skipped"

    game = db.query(Game).filter_by(cfbd_id=payload["id"]).first()
    action = "updated" if game else "added"
    if game is None:
        game = Game(cfbd_id=payload["id"])
        db.add(game)

    game.season = season
    game.week = payload.get("week", 0)
    game.season_type = season_type
    game.start_date = parse_start_date(payload.get("startDate"))
    game.neutral_site = bool(payload.get("neutralSite", False))
    game.conference_game = bool(payload.get("conferenceGame", False))
    game.completed = bool(payload.get("completed", False))
    game.venue = payload.get("venue")
    game.home_team_id = home_team.id
    game.away_team_id = away_team.id
    game.home_points = payload.get("homePoints")
    game.away_points = payload.get("awayPoints")
    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CFBD games into the database")
    parser.add_argument("--year", type=int, required=True, help="Season year, e.g. 2026")
    parser.add_argument("--week", type=int, default=None, help="Single week only (omit for full season)")
    parser.add_argument(
        "--season-type", default="regular", choices=["regular", "postseason"], help="Default: regular"
    )
    args = parser.parse_args()

    init_db()

    print(f"Fetching {args.season_type} games for {args.year}" + (f" week {args.week}" if args.week else "") + "...")
    games = fetch_games(args.year, args.season_type, args.week)
    print(f"Got {len(games)} games from CFBD.")

    db = SessionLocal()
    added = updated = skipped = 0
    try:
        for payload in games:
            result = upsert_game(db, payload, season=args.year, season_type=args.season_type)
            if result == "added":
                added += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1
        db.commit()
        print(
            f"\nDone: {added} added, {updated} updated, {skipped} skipped "
            f"(team not in database), {len(games)} total from CFBD."
        )
        if skipped:
            print(
                "Skipped games involve a team not yet in your teams table -- "
                "check backend/data/teams.csv / scripts/seed_teams.py if you expect it to be there."
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
