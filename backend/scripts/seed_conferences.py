"""
One-time (or rarely-rerun) seed script: load conference reference data from
a local CSV into the database. No CFBD API calls -- conferences almost never
change, so this data is meant to be typed/gathered once and just live in
the repo as backend/data/conferences.csv.

Expected CSV columns (header names, case-insensitive):
    conference_id, name, full_name, abbreviation, classification

Usage (run from backend/):
    python -m scripts.seed_conferences
    python -m scripts.seed_conferences --file data/my_conferences.csv

Safe to rerun: matches existing rows by cfbd_id (from conference_id) and
updates them in place instead of creating duplicates.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Conference  # noqa: E402

DEFAULT_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "conferences.csv")


def load_rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # normalize headers to lowercase so "Classification" vs "classification" doesn't matter
        reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
        return [row for row in reader]


def upsert_conference(db, row: dict) -> str:
    """Returns 'created' or 'updated' for the summary count."""
    cfbd_id = int(row["conference_id"])
    name = row["name"].strip()
    full_name = (row.get("full_name") or "").strip() or None
    abbreviation = (row.get("abbreviation") or "").strip() or None
    classification = (row.get("classification") or "").strip().lower() or None

    conf = db.query(Conference).filter_by(cfbd_id=cfbd_id).first()
    action = "updated" if conf else "created"

    if conf is None:
        conf = Conference(cfbd_id=cfbd_id)
        db.add(conf)

    conf.name = name
    conf.full_name = full_name
    conf.abbreviation = abbreviation
    conf.classification = classification

    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the conferences table from a CSV file")
    parser.add_argument("--file", default=DEFAULT_CSV_PATH, help=f"Path to CSV (default: {DEFAULT_CSV_PATH})")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise SystemExit(f"CSV not found: {args.file}\nPut your file there, or pass --file <path>.")

    init_db()

    rows = load_rows(args.file)
    print(f"Read {len(rows)} rows from {args.file}")

    db = SessionLocal()
    created = updated = 0
    try:
        for row in rows:
            action = upsert_conference(db, row)
            if action == "created":
                created += 1
            else:
                updated += 1
        db.commit()
        print(f"Done: {created} created, {updated} updated, {len(rows)} total.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
