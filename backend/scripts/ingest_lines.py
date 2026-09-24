"""
Standalone script: pull betting lines from the CollegeFootballData API and
upsert them into the database, one row per (game, provider).

Usage (run from backend/):
    python -m scripts.ingest_lines --year 2026
    python -m scripts.ingest_lines --year 2026 --week 3
    python -m scripts.ingest_lines --year 2026 --season-type postseason

Requires CFBD_API_KEY to be set (backend/.env, same as the FastAPI app).

Run scripts.ingest_games first: lines are only attached to Game rows that
already exist there (matched by CFBD game id). Lines for a game not yet in
the database are skipped and printed to stdout, with a summary count at the
end -- this script never creates a Game row on its own.

This is the other half of US-03 ("the model's win probability ... next to
the market spread/moneyline"): app/routers/odds.py reads the `lines` table
this script writes, alongside the Game rows ingest_games.py writes (which
already include upcoming, not-yet-played games -- CFBD's /games endpoint
returns the full season schedule, not just completed results).

Note on field names: this targets CFBD's commonly-documented /lines schema
(id, lines: [{provider, spread, overUnder, homeMoneyline, awayMoneyline}]).
As with ingest_games.py, CFBD's API has multiple versions in the wild --
confirm these field names against a live response (e.g. via /docs on
api.collegefootballdata.com or a quick curl) before relying on this for
real ingestion, since this sandbox has no network path to verify.
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Game, Line  # noqa: E402

load_dotenv()

CFBD_BASE_URL = "https://api.collegefootballdata.com"


def fetch_lines(year: int, season_type: str, week: int | None) -> list[dict]:
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        raise RuntimeError("CFBD_API_KEY is not set (check backend/.env)")

    params = {"year": year, "seasonType": season_type}
    if week is not None:
        params["week"] = week

    resp = requests.get(
        f"{CFBD_BASE_URL}/lines",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upsert_lines_for_game(db: Session, payload: dict) -> tuple[str, int]:
    """
    Upsert every provider's line for one CFBD /lines entry (a game plus its
    `lines` array). Returns (status, count):
      status -- 'added' if any new Line row was created, 'updated' if only
                existing rows were refreshed, 'skipped' if the game itself
                isn't in the database yet.
      count  -- how many provider rows were written (0 for 'skipped', or if
                CFBD returned no lines for this game yet).
    """
    game = db.query(Game).filter_by(cfbd_id=payload["id"]).first()
    if game is None:
        print(f"  skipping lines for game {payload.get('id')}: game not in database yet")
        return "skipped", 0

    written = 0
    any_new = False
    for line_payload in payload.get("lines", []):
        provider = line_payload.get("provider")
        if not provider:
            continue  # can't upsert on (game_id, provider) without a provider name

        line = db.query(Line).filter_by(game_id=game.id, provider=provider).first()
        if line is None:
            line = Line(game_id=game.id, provider=provider)
            db.add(line)
            any_new = True

        line.spread = line_payload.get("spread")
        line.over_under = line_payload.get("overUnder")
        line.home_moneyline = line_payload.get("homeMoneyline")
        line.away_moneyline = line_payload.get("awayMoneyline")
        written += 1

    return ("added" if any_new else "updated"), written


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CFBD betting lines into the database")
    parser.add_argument("--year", type=int, required=True, help="Season year, e.g. 2026")
    parser.add_argument("--week", type=int, default=None, help="Single week only (omit for full season)")
    parser.add_argument(
        "--season-type", default="regular", choices=["regular", "postseason"], help="Default: regular"
    )
    args = parser.parse_args()

    init_db()

    print(f"Fetching {args.season_type} lines for {args.year}" + (f" week {args.week}" if args.week else "") + "...")
    games_with_lines = fetch_lines(args.year, args.season_type, args.week)
    print(f"Got lines for {len(games_with_lines)} game(s) from CFBD.")

    db = SessionLocal()
    added = updated = skipped = 0
    lines_written = 0
    try:
        for payload in games_with_lines:
            status, count = upsert_lines_for_game(db, payload)
            lines_written += count
            if status == "added":
                added += 1
            elif status == "updated":
                updated += 1
            else:
                skipped += 1
        db.commit()
        print(
            f"\nDone: {lines_written} line row(s) written across {added} new + {updated} updated game(s), "
            f"{skipped} skipped (game not in database yet), {len(games_with_lines)} total games from CFBD."
        )
        if skipped:
            print(
                "Skipped games aren't ingested yet -- run scripts.ingest_games for the "
                "same year/week first, then re-run this script."
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
