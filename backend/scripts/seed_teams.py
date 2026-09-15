"""
One-time (or rarely-rerun) seed script: load team reference data from a
local CSV into the database. No CFBD API calls.

Expected CSV columns (header names, case-insensitive):
    school_id, school, school_mascot, abbreviation, conference_id, division,
    classification, color, alternate_color, logo, stadium_name, school_city,
    school_state, stadium_latitude, stadium_longitude, stadium_elevation,
    stadium_capacity, stadium_grass, stadium_dome

NOTE: "school" (the team's name, e.g. "Alabama") is assumed to be a column
in your CSV. If your file doesn't have it under that exact header, either
rename the column or adjust FIELD spelled out below.

conference_id here is CFBD's conference ID, matched against
Conference.cfbd_id -- so run seed_conferences.py first, or teams will be
created with no conference linked (a warning is printed, not an error).

Usage (run from backend/):
    python -m scripts.seed_teams
    python -m scripts.seed_teams --file data/my_teams.csv
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Conference, Team  # noqa: E402

DEFAULT_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "teams.csv")

REQUIRED_COLUMNS = {"school_id", "school"}


def load_rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
        rows = [row for row in reader]

    if rows:
        missing = REQUIRED_COLUMNS - set(rows[0].keys())
        if missing:
            raise SystemExit(
                f"CSV is missing required column(s): {sorted(missing)}. "
                f"Found columns: {sorted(rows[0].keys())}"
            )
    return rows


def parse_bool(raw: str | None) -> bool | None:
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().upper() == "TRUE"


def parse_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(float(raw))  # handles "65000.0"-style values too
    except ValueError:
        return None


def clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def upsert_team(db, row: dict, warnings: list[str]) -> str:
    """Returns 'created' or 'updated' for the summary count."""
    cfbd_id = int(row["school_id"])
    school = row["school"].strip()

    conference_row_id = None
    raw_conf_id = clean(row.get("conference_id"))
    if raw_conf_id is not None:
        conf = db.query(Conference).filter_by(cfbd_id=int(float(raw_conf_id))).first()
        if conf:
            conference_row_id = conf.id
        else:
            warnings.append(f"  {school}: no Conference found for conference_id={raw_conf_id} (run seed_conferences.py first?)")

    team = db.query(Team).filter_by(cfbd_id=cfbd_id).first()
    action = "updated" if team else "created"

    if team is None:
        team = Team(cfbd_id=cfbd_id)
        db.add(team)

    team.school = school
    team.mascot = clean(row.get("school_mascot"))
    team.abbreviation = clean(row.get("abbreviation"))
    team.classification = (clean(row.get("classification")) or "").lower() or None
    team.division = clean(row.get("division"))
    team.logo_url = clean(row.get("logo"))
    team.color = clean(row.get("color"))
    team.alternate_color = clean(row.get("alternate_color"))
    team.school_city = clean(row.get("school_city"))
    team.school_state = clean(row.get("school_state"))
    team.stadium_name = clean(row.get("stadium_name"))
    team.stadium_latitude = parse_float(row.get("stadium_latitude"))
    team.stadium_longitude = parse_float(row.get("stadium_longitude"))
    team.stadium_elevation = parse_float(row.get("stadium_elevation"))
    team.stadium_capacity = parse_int(row.get("stadium_capacity"))
    team.stadium_grass = parse_bool(row.get("stadium_grass"))
    team.stadium_dome = parse_bool(row.get("stadium_dome"))
    team.conference_id = conference_row_id

    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the teams table from a CSV file")
    parser.add_argument("--file", default=DEFAULT_CSV_PATH, help=f"Path to CSV (default: {DEFAULT_CSV_PATH})")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise SystemExit(f"CSV not found: {args.file}\nPut your file there, or pass --file <path>.")

    init_db()

    rows = load_rows(args.file)
    print(f"Read {len(rows)} rows from {args.file}")

    db = SessionLocal()
    created = updated = 0
    warnings: list[str] = []
    try:
        for row in rows:
            action = upsert_team(db, row, warnings)
            if action == "created":
                created += 1
            else:
                updated += 1
        db.commit()
        print(f"Done: {created} created, {updated} updated, {len(rows)} total.")
        if warnings:
            print(f"\n{len(warnings)} warning(s):")
            for w in warnings:
                print(w)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
