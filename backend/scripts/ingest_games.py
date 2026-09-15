"""
Standalone script: pull games from the CollegeFootballData API and upsert
them into the database.

Usage (run from backend/):
    python -m scripts.ingest_games --year 2026
    python -m scripts.ingest_games --year 2026 --week 3
    python -m scripts.ingest_games --year 2026 --season-type postseason

Requires CFBD_API_KEY to be set (backend/.env, same as the FastAPI app).

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


def get_or_create_team(db: Session, cfbd_id: int | None, school: str | None) -> Team | None:
    """
    Minimal team upsert so games have a valid FK target. This only fills in
    cfbd_id + school; conference, mascot, and logo are meant to come from a
    dedicated /teams/fbs sync script (a natural next script, not this one).
    """
    if cfbd_id is None or not school:
        return None

    team = db.query(Team).filter_by(cfbd_id=cfbd_id).first()
    if team:
        return team

    team = Team(cfbd_id=cfbd_id, school=school)
    db.add(team)
    db.flush()  # get team.id without a full commit
    return team


def parse_start_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def upsert_game(db: Session, payload: dict, season: int, season_type: str) -> None:
    home_team = get_or_create_team(db, payload.get("homeId"), payload.get("homeTeam"))
    away_team = get_or_create_team(db, payload.get("awayId"), payload.get("awayTeam"))

    if home_team is None or away_team is None:
        print(f"  skipping game {payload.get('id')}: missing home/away team id")
        return

    game = db.query(Game).filter_by(cfbd_id=payload["id"]).first()
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
    try:
        for payload in games:
            upsert_game(db, payload, season=args.year, season_type=args.season_type)
        db.commit()
        print(f"Upserted {len(games)} games (and any new teams they referenced).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
