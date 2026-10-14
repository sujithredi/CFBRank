"""
Standalone script: Monte Carlo simulation of the rest of the regular season.

Replays every unplayed regular-season game 10,000 times (see
app/season_simulation.py for the method and assumptions) and reports, per
team: average wins, average losses, Bowl% (bowl eligible = 6+ wins),
Undefeated% (finishes the regular season with no losses), Title% (plays in its
conference championship game), Champ% (wins it), Playoff% (is selected for the
12-team College Football Playoff field) and, for the playoff games, Bye% (top-4
seed), QF% (plays in the quarterfinals), Semi%, Final% and CFP champ% (wins the
national title).

The remaining games are played one week at a time, and after each simulated
week the ratings are re-fit with that week's simulated scores (see
app/weekly_ratings.py), so each week is simulated with up-to-date ratings.
Use --fixed-ratings to keep today's ratings for every week instead, e.g. to
see how much the weekly updating changes the answers.

Conference championship games are simulated after each regular season, using
each conference's own tiebreakers (app/conference_championships.py). They are
never counted in a team's wins, losses, Bowl% or Undefeated%.

The playoff field is chosen after each simulated season (app/playoff.py): the ACC,
Big Ten, SEC and Big 12 champions, the best Group of 6 champion, Notre Dame if it is a
top-12 team, and the remaining spots at large, the last groups picked by the neural
network trained on data/playoff_data.csv from each team's strength of schedule and
record. The field is then seeded by overall rating and the 12-team bracket is played
out (app/playoff_bracket.py).

Reads the latest power-rating snapshot and the unplayed games already in the
database, so run these first if they are stale:
    python -m scripts.ingest_games --year 2026
    python -m scripts.compute_rankings --year 2026

Usage (run from backend/):
    python -m scripts.simulate_season
    python -m scripts.simulate_season --year 2026 --seed 42
    python -m scripts.simulate_season --top 25
    python -m scripts.simulate_season --sims 2000 --csv season_sim.csv
    python -m scripts.simulate_season --include-fcs
    python -m scripts.simulate_season --fixed-ratings --no-save

By default the results are also saved to the database (season_projections
table), which is what the rankings page shows -- every team is saved, whatever
is printed. Pass --no-save for a throwaway run (e.g. with a different --sims).

Only FBS teams are printed by default (Bowl% doesn't apply to FCS teams);
--include-fcs adds them. --csv writes the same rows that are printed.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

from app.conference_championships import DISCLAIMERS  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.season_simulation import N_SIMULATIONS, run_season_simulation, save_season_projections  # noqa: E402


def _pct(value) -> str:
    return "   n/a" if value is None or value != value else f"{value:5.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate the rest of the regular season")
    parser.add_argument("--year", type=int, default=None, help="Season year (default: latest with ratings)")
    parser.add_argument("--sims", type=int, default=N_SIMULATIONS, help=f"Number of simulations (default: {N_SIMULATIONS:,})")
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for a reproducible run")
    parser.add_argument("--top", type=int, default=None, help="Only print the top N teams by average wins")
    parser.add_argument("--include-fcs", action="store_true", help="Include FCS teams in the output")
    parser.add_argument("--csv", default=None, help="Also write the printed rows to this CSV path")
    parser.add_argument("--no-save", action="store_true", help="Don't write the results to the database")
    parser.add_argument(
        "--fixed-ratings", action="store_true",
        help="Don't re-fit the ratings after each simulated week (use today's ratings throughout)",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        started = time.time()
        try:
            season, week, results = run_season_simulation(
                db, args.year, args.sims, args.seed, update_ratings=not args.fixed_ratings
            )
        except ValueError as error:
            sys.exit(f"error: {error}")
        elapsed = time.time() - started

        saved = 0
        if not args.no_save:
            saved = save_season_projections(db, season, week, results, args.sims)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if not args.include_fcs:
        results = results[results["classification"] == "fbs"].reset_index(drop=True)
    if args.top is not None:
        results = results.head(args.top)

    print(
        f"Simulated the rest of the {season} regular season {args.sims:,} times "
        f"(ratings through week {week}, "
        + ("held fixed" if args.fixed_ratings else "re-fit after each simulated week")
        + f") in {elapsed:.1f}s.\n"
    )
    print(
        f"  {'':>3}  {'team':<24} {'conf':<18} {'now':>6} {'avg W':>6} {'avg L':>6} "
        f"{'bowl%':>7} {'undef%':>7} {'title%':>7} {'champ%':>7} {'playoff%':>9} "
        f"{'bye%':>7} {'qf%':>7} {'semi%':>7} {'final%':>7} {'cfp champ%':>11}"
    )
    for rank, row in enumerate(results.itertuples(index=False), start=1):
        print(
            f"  {rank:>3}. {row.team:<24} {row.conference[:18]:<18} {row.wins:>3}-{row.losses:<2} "
            f"{row.avg_wins:6.2f} {row.avg_losses:6.2f} {_pct(row.bowl_pct):>7} {_pct(row.undefeated_pct):>7} "
            f"{_pct(row.title_game_pct):>7} {_pct(row.conf_champ_pct):>7} {_pct(row.playoff_pct):>9} "
            f"{_pct(row.cfp_bye_pct):>7} {_pct(row.cfp_quarterfinal_pct):>7} {_pct(row.cfp_semifinal_pct):>7} "
            f"{_pct(row.cfp_final_pct):>7} {_pct(row.cfp_champion_pct):>11}"
        )

    print("\nConference championship notes:")
    for note in DISCLAIMERS:
        print(f"  * {note}")

    if not args.no_save:
        print(f"\nSaved {saved} team projection(s) for {season} week {week} to the database.")

    if args.csv:
        results.round({"avg_wins": 3, "avg_losses": 3, "bowl_pct": 2, "undefeated_pct": 2, "title_game_pct": 2, "conf_champ_pct": 2, "playoff_pct": 2, "cfp_bye_pct": 2, "cfp_quarterfinal_pct": 2, "cfp_semifinal_pct": 2, "cfp_final_pct": 2, "cfp_champion_pct": 2}).to_csv(args.csv, index=False)
        print(f"\nWrote {len(results)} row(s) to {args.csv}")


if __name__ == "__main__":
    main()
