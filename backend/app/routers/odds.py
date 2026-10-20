"""
GET /api/odds/weekly
 
Reads upcoming (not-yet-played) games for a season/week, simulates each one
NUM_SIMULATIONS (1000) times from the latest PowerRating snapshot for each
team, and lines the results up against market betting lines (US-03: "the
model's win probability ... next to the market spread/moneyline").

Each simulation is a full game from app/simulation.py (the same score
simulator as the matchup page and the season projections), so the model's
numbers are simply averages over the simulated games:

    win probability  the share of simulations the home team won
    projected points the average points each team scored
    margin           the average of home score minus away score
    total            the average of home score plus away score

The home team gets the usual home-field edge unless the game is at a neutral
site. Each game's simulations are seeded from the game's id, so a given game
shows the same numbers on every refresh until its teams' ratings change.

Because of that, the simulations are memoized per game and rating values (see
cached_simulate_matchup): the first request after a ratings change pays for them once, and
every later request, however many arrive at once, reuses the stored results. The endpoint also
rate-limits each client (ODDS_RATE_LIMIT_PER_MINUTE) and marks real responses cacheable by
browsers and CDNs for a few minutes.
 
Falls back to a small hardcoded response if there's nothing usable in
the database yet (no games ingested, no ratings computed, or no
upcoming games this week), so the frontend never gets a 500/empty page
while the pipeline is being set up -- same pattern as app/rankings.py.
 
Data flow this endpoint depends on:
    scripts/ingest_games.py  -- writes Game rows, including upcoming ones
    scripts/ingest_lines.py  -- writes Line rows (market odds) per game
    scripts/compute_rankings.py -- writes PowerRating snapshots used here
"""
 
import os
import random
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import NamedTuple
 
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session, aliased
 
from app.database import get_db
from app.models import Game, Line, PowerRating, Team
from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE
from app.ratelimit import RateLimiter, enforce
from app.schemas import GameOdds, WeeklyOddsResponse
from app.simulation import load_sorted_scores, simulate_game
 
 
def _env_int(name: str, default: int) -> int:
    """An int from the environment; a missing or malformed value falls back to `default`."""
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# Per-client limit on this endpoint, per minute (0 turns it off). This is a backstop; the
# main protection is the simulation cache below, and a reverse proxy / CDN should rate-limit
# too (see app/ratelimit.py and docs/SETUP.md).
ODDS_RATE_LIMIT_PER_MINUTE = _env_int("ODDS_RATE_LIMIT_PER_MINUTE", 60)
_odds_limiter = RateLimiter(max_requests=ODDS_RATE_LIMIT_PER_MINUTE, window_seconds=60)

# How long browsers and CDNs may reuse a response built from real data. The numbers only
# change when the refresh job runs (twice a week), so a few minutes of staleness is harmless.
ODDS_CACHE_CONTROL = "public, max-age=300"


def _enforce_rate_limit(request: Request) -> None:
    enforce(_odds_limiter, request)


def reset_rate_limiter() -> None:
    """Forget every client's request history (used by tests)."""
    _odds_limiter.reset()


router = APIRouter(prefix="/api/odds", tags=["odds"])

# How many times each game is simulated. A win probability is the share of these
# simulations a team wins, so it moves in steps of 1 / NUM_SIMULATIONS.
NUM_SIMULATIONS = 1000
 
_FALLBACK_ODDS = WeeklyOddsResponse(
    season=2026,
    week=3,
    num_simulations=NUM_SIMULATIONS,
    games=[
        GameOdds(
            game_id=401520123,
            start_date=datetime.now(timezone.utc),
            home_team="Alabama",
            away_team="Wisconsin",
            model_home_points=36.2,
            model_away_points=18.3,
            model_predicted_margin=17.9,
            model_total=54.5,
            model_home_win_prob=0.81,
            market_spread=-13.5,
            market_home_moneyline=-650,
            market_away_moneyline=480,
            delta=-0.0567,
        ),
        GameOdds(
            game_id=401520124,
            start_date=datetime.now(timezone.utc),
            home_team="Georgia",
            away_team="Kentucky",
            model_home_points=33.4,
            model_away_points=20.3,
            model_predicted_margin=13.1,
            model_total=53.7,
            model_home_win_prob=0.73,
            market_spread=-10.0,
            market_home_moneyline=-420,
            market_away_moneyline=340,
            delta=-0.0777,
        ),
    ],
)
 
 
def _resolve_season_week(
    db: Session, season: int | None, week: int | None, season_type: str
) -> tuple[int, int] | None:
    """
    Fill in whichever of (season, week) is missing by finding the nearest
    upcoming (not-yet-played) game on file. None if there isn't one --
    e.g. games haven't been ingested yet, or every ingested game for this
    season_type is already completed.
    """
    if season is not None and week is not None:
        return season, week
 
    query = db.query(Game.season, Game.week).filter(
        Game.season_type == season_type, Game.completed.is_(False)
    )
    if season is not None:
        query = query.filter(Game.season == season)
 
    next_game = query.order_by(Game.start_date.asc()).first()
    if next_game is None:
        print(
            f"[odds] no upcoming (completed=False) {season_type!r} game found in the games table"
            + (f" for season {season}" if season is not None else " for any season")
            + " -- falling back to mock odds. Run `python -m scripts.ingest_games --year <year>` "
            "(from backend/) to pull the season schedule, including games that haven't been played yet."
        )
        return None
    return season if season is not None else next_game[0], week if week is not None else next_game[1]
 
 
def _snapshot_order(rating: PowerRating) -> tuple:
    """Sort key for 'which snapshot is the latest': the later week, then the later computed_at."""
    return (rating.week, rating.computed_at or datetime.min)


def _latest_ratings(db: Session, team_ids: set[int], season: int, through_week: int) -> dict[int, PowerRating]:
    """
    Each team's most recent PowerRating snapshot at or before `through_week`, keyed by team id.

    One query for every team in the week. This used to be one query per team per game, which
    turned a single request for a full week into hundreds of database round trips.
    """
    if not team_ids:
        return {}
    rows = (
        db.query(PowerRating)
        .filter(
            PowerRating.team_id.in_(team_ids),
            PowerRating.season == season,
            PowerRating.week <= through_week,
        )
        .all()
    )
    latest: dict[int, PowerRating] = {}
    for row in rows:
        best = latest.get(row.team_id)
        if best is None or _snapshot_order(row) > _snapshot_order(best):
            latest[row.team_id] = row
    return latest


def _best_lines(db: Session, game_ids: list[int]) -> dict[int, Line]:
    """
    One line per game, keyed by game id (games with no line are absent). Prefers the 'consensus'
    provider when CFBD gives more than one line for a game, otherwise the first provider by name.

    The query used to have no ORDER BY, so "first" was whatever order the database happened to
    return; SQLite returns a game's lines in the order of the (game_id, provider) unique index,
    which is by provider name. Ordering by provider says that out loud (and keeps the numbers the
    page already shows), and makes the choice the same on any database.
    """
    if not game_ids:
        return {}
    by_game: dict[int, list[Line]] = {}
    for line in db.query(Line).filter(Line.game_id.in_(game_ids)).order_by(Line.provider).all():
        by_game.setdefault(line.game_id, []).append(line)
    return {
        game_id: next((line for line in lines if line.provider == "consensus"), lines[0])
        for game_id, lines in by_game.items()
    }


def _implied_home_prob(home_moneyline: int | None) -> float | None:
    """
    American moneyline -> implied win probability. This is the raw
    (vig-included) implied probability, not de-vigged against the
    away-side line -- a fine MVP approximation for a directional
    "does the model disagree with the market" delta.
    """
    if home_moneyline is None:
        return None
    if home_moneyline < 0:
        return (-home_moneyline) / (-home_moneyline + 100)
    return 100 / (home_moneyline + 100)
 
 
class SimulatedGame(NamedTuple):
    """Averages over the simulated games, from the home team's side."""

    home_win_prob: float  # share of simulations the home team won, 0-1
    home_points: float
    away_points: float


def simulate_matchup(
    home: PowerRating,
    away: PowerRating,
    neutral_site: bool,
    seed: int,
    sorted_scores,
    num_simulations: int = NUM_SIMULATIONS,
) -> SimulatedGame:
    """
    Play `home` vs `away` `num_simulations` times with app.simulation.simulate_game and average.

    Both ratings need an offense and a defense rating. The home team gets
    DEFAULT_HOME_FIELD_ADVANTAGE unless the game is at a neutral site. `seed` makes the run
    reproducible: the same teams and ratings always give the same numbers.
    """
    rng = random.Random(seed)
    home_edge = 0.0 if neutral_site else DEFAULT_HOME_FIELD_ADVANTAGE

    home_wins = 0
    home_points = 0
    away_points = 0
    for _ in range(num_simulations):
        result = simulate_game(
            home.offense_rating, home.defense_rating, away.offense_rating, away.defense_rating,
            sorted_scores=sorted_scores, rng=rng, home_field_advantage=home_edge,
        )
        home_wins += result["score_a"] > result["score_b"]  # simulate_game never ties
        home_points += result["score_a"]
        away_points += result["score_b"]

    return SimulatedGame(home_wins / num_simulations, home_points / num_simulations, away_points / num_simulations)


# ---- simulation cache ---------------------------------------------------------
#
# Simulating a game 1,000 times is the only expensive step in this endpoint, and its result is
# a pure function of (game id seed, home-site flag, the four ratings, number of simulations):
# the RNG is seeded from the game id, so repeating the work can only reproduce the same numbers.
# So each game's result is memoized under exactly those inputs. Keying on the rating *values*
# (not a timestamp) means a recomputed rating that comes out different is a cache miss by
# construction, while an unchanged one keeps hitting the cache after the refresh job reruns.
# The score table from app.simulation is read once per process and never changes while it runs,
# so it is not part of the key. The cache is per process: with several workers each one builds
# its own copy, which costs one cold run per worker per week and nothing more.

# One week has at most ~150 games and a season ~1,500, so this holds several weeks' worth.
SIMULATION_CACHE_MAX_ENTRIES = 5_000

_simulation_cache: OrderedDict[tuple, SimulatedGame] = OrderedDict()
_simulation_cache_lock = threading.Lock()  # guards _simulation_cache
_simulation_compute_lock = threading.Lock()  # lets only one request run a simulation at a time


def clear_simulation_cache() -> None:
    """Drop every cached simulation (used by tests)."""
    with _simulation_cache_lock:
        _simulation_cache.clear()


def _simulation_key(
    home: PowerRating, away: PowerRating, neutral_site: bool, seed: int, num_simulations: int
) -> tuple:
    return (
        seed,
        bool(neutral_site),
        num_simulations,
        home.offense_rating,
        home.defense_rating,
        away.offense_rating,
        away.defense_rating,
    )


def _cache_get(key: tuple) -> SimulatedGame | None:
    with _simulation_cache_lock:
        cached = _simulation_cache.get(key)
        if cached is not None:
            _simulation_cache.move_to_end(key)  # most recently used
        return cached


def cached_simulate_matchup(
    home: PowerRating,
    away: PowerRating,
    neutral_site: bool,
    seed: int,
    sorted_scores,
    num_simulations: int = NUM_SIMULATIONS,
) -> SimulatedGame:
    """
    `simulate_matchup`, remembered. The first call for a given game and pair of ratings runs the
    simulations; every later call returns the stored result in microseconds.

    Concurrent requests for games nobody has simulated yet take turns on a lock and re-check the
    cache once they get it, so a burst of identical requests (or an attacker repeating one) costs
    one simulation per game, not one per request.
    """
    key = _simulation_key(home, away, neutral_site, seed, num_simulations)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    with _simulation_compute_lock:
        cached = _cache_get(key)  # another request may have finished it while this one waited
        if cached is not None:
            return cached

        result = simulate_matchup(home, away, neutral_site, seed, sorted_scores, num_simulations)
        with _simulation_cache_lock:
            _simulation_cache[key] = result
            while len(_simulation_cache) > SIMULATION_CACHE_MAX_ENTRIES:
                _simulation_cache.popitem(last=False)  # least recently used
        return result


def _fallback(response: Response) -> WeeklyOddsResponse:
    """The placeholder rows, marked uncacheable so a CDN or browser never keeps them."""
    response.headers["Cache-Control"] = "no-store"
    return _FALLBACK_ODDS


@router.get("/weekly", response_model=WeeklyOddsResponse, dependencies=[Depends(_enforce_rate_limit)])
def get_weekly_odds(
    response: Response,
    season: int | None = None,
    week: int | None = None,
    season_type: str = "regular",
    db: Session = Depends(get_db),
):
    # Real data may be reused by browsers and CDNs for a few minutes; the placeholder rows
    # may not, and _fallback() overrides this header for them.
    response.headers["Cache-Control"] = ODDS_CACHE_CONTROL

    resolved = _resolve_season_week(db, season, week, season_type)
    if resolved is None:
        return _fallback(response)
    season, week = resolved
 
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)
 
    rows = (
        db.query(Game, HomeTeam, AwayTeam)
        .join(HomeTeam, Game.home_team_id == HomeTeam.id)
        .join(AwayTeam, Game.away_team_id == AwayTeam.id)
        .filter(
            Game.season == season,
            Game.week == week,
            Game.season_type == season_type,
            Game.completed.is_(False),
        )
        .order_by(Game.start_date.asc())
        .all()
    )
    if not rows:
        print(
            f"[odds] resolved season={season} week={week} season_type={season_type!r}, but no games "
            "matched that exact combination -- falling back to mock odds."
        )
        return _fallback(response)
 
    # Everything the loop needs from the database, fetched up front (see _latest_ratings).
    team_ids = {game.home_team_id for game, _, _ in rows} | {game.away_team_id for game, _, _ in rows}
    ratings = _latest_ratings(db, team_ids, season, week - 1)
    lines = _best_lines(db, [game.id for game, _, _ in rows])

    sorted_scores = load_sorted_scores()
    games: list[GameOdds] = []
    skipped_no_rating = 0
    for game, home_team, away_team in rows:
        home_rating = ratings.get(game.home_team_id)
        away_rating = ratings.get(game.away_team_id)
        if (
            home_rating is None
            or away_rating is None
            or None in (home_rating.offense_rating, home_rating.defense_rating)
            or None in (away_rating.offense_rating, away_rating.defense_rating)
        ):
            # No rating history yet for one of these teams (e.g. week 1, or compute_rankings hasn't
            # run), or only an old snapshot from before the offense/defense split -- the simulator
            # needs both, so skip rather than guess.
            skipped_no_rating += 1
            continue

        simulated = cached_simulate_matchup(
            home_rating, away_rating, bool(game.neutral_site), seed=game.cfbd_id, sorted_scores=sorted_scores
        )
        model_prob = simulated.home_win_prob
        margin = simulated.home_points - simulated.away_points
 
        line = lines.get(game.id)
        market_spread = line.spread if line else None
        market_home_ml = line.home_moneyline if line else None
        market_away_ml = line.away_moneyline if line else None
 
        implied_prob = _implied_home_prob(market_home_ml)
        delta = round(model_prob - implied_prob, 4) if implied_prob is not None else None
 
        games.append(
            GameOdds(
                game_id=game.cfbd_id,
                start_date=game.start_date or datetime.now(timezone.utc),
                home_team=home_team.school,
                away_team=away_team.school,
                home_logo_url=home_team.logo_url,
                away_logo_url=away_team.logo_url,
                model_home_points=round(simulated.home_points, 1),
                model_away_points=round(simulated.away_points, 1),
                model_predicted_margin=round(margin, 1),
                model_total=round(simulated.home_points + simulated.away_points, 1),
                model_home_win_prob=round(model_prob, 4),
                market_spread=market_spread,
                market_home_moneyline=market_home_ml,
                market_away_moneyline=market_away_ml,
                delta=delta,
            )
        )
 
    if not games:
        print(
            f"[odds] found {len(rows)} upcoming game(s) for season={season} week={week}, but all "
            f"{skipped_no_rating} were skipped for missing PowerRating history (or offense/defense ratings) on one/both teams -- "
            f"falling back to mock odds. Run `python -m scripts.compute_rankings --year {season} "
            f"--through-week {week - 1}` (from backend/) so ratings exist going into this week."
        )
        return _fallback(response)
 
    return WeeklyOddsResponse(season=season, week=week, num_simulations=NUM_SIMULATIONS, games=games)