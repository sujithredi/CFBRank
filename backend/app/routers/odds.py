"""
GET /api/odds/weekly
 
Reads upcoming (not-yet-played) games for a season/week, computes the
model's win probability from the latest PowerRating snapshot for each
team, and lines them up against market betting lines (US-03: "the
model's win probability ... next to the market spread/moneyline").
 
Falls back to a small hardcoded response if there's nothing usable in
the database yet (no games ingested, no ratings computed, or no
upcoming games this week), so the frontend never gets a 500/empty page
while the pipeline is being set up -- same pattern as app/rankings.py.
 
Data flow this endpoint depends on:
    scripts/ingest_games.py  -- writes Game rows, including upcoming ones
    scripts/ingest_lines.py  -- writes Line rows (market odds) per game
    scripts/compute_rankings.py -- writes PowerRating snapshots used here
"""
 
from datetime import datetime, timezone
 
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, aliased
 
from app.database import get_db
from app.models import Game, Line, PowerRating, Team
from app.ranking import expected_margin, win_probability_from_margin
from app.schemas import GameOdds, WeeklyOddsResponse
 
router = APIRouter(prefix="/api/odds", tags=["odds"])
 
_FALLBACK_ODDS = WeeklyOddsResponse(
    season=2026,
    week=3,
    games=[
        GameOdds(
            game_id=401520123,
            start_date=datetime.now(timezone.utc),
            home_team="Alabama",
            away_team="Wisconsin",
            model_predicted_margin=17.9,
            model_home_win_prob=0.88,
            market_spread=-13.5,
            market_home_moneyline=-650,
            market_away_moneyline=480,
            delta=0.04,
        ),
        GameOdds(
            game_id=401520124,
            start_date=datetime.now(timezone.utc),
            home_team="Georgia",
            away_team="Kentucky",
            model_predicted_margin=13.1,
            model_home_win_prob=0.81,
            market_spread=-10.0,
            market_home_moneyline=-420,
            market_away_moneyline=340,
            delta=-0.03,
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
 
 
def _latest_rating(db: Session, team_id: int, season: int, through_week: int) -> PowerRating | None:
    """Most recent PowerRating snapshot for this team at or before through_week."""
    return (
        db.query(PowerRating)
        .filter(
            PowerRating.team_id == team_id,
            PowerRating.season == season,
            PowerRating.week <= through_week,
        )
        .order_by(PowerRating.week.desc(), PowerRating.computed_at.desc())
        .first()
    )
 
 
def _best_line(db: Session, game_id: int) -> Line | None:
    """Prefer the 'consensus' provider when CFBD gives more than one line for a game."""
    lines = db.query(Line).filter(Line.game_id == game_id).all()
    if not lines:
        return None
    return next((line for line in lines if line.provider == "consensus"), lines[0])
 
 
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
 
 
@router.get("/weekly", response_model=WeeklyOddsResponse)
def get_weekly_odds(
    season: int | None = None, week: int | None = None, season_type: str = "regular", db: Session = Depends(get_db)
):
    resolved = _resolve_season_week(db, season, week, season_type)
    if resolved is None:
        return _FALLBACK_ODDS
    season, week = resolved
 
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)
 
    rows = (
        db.query(Game, HomeTeam.school, AwayTeam.school)
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
        return _FALLBACK_ODDS
 
    games: list[GameOdds] = []
    skipped_no_rating = 0
    for game, home_school, away_school in rows:
        home_rating = _latest_rating(db, game.home_team_id, season, week - 1)
        away_rating = _latest_rating(db, game.away_team_id, season, week - 1)
        if home_rating is None or away_rating is None:
            # No rating history yet for one of these teams (e.g. week 1, or
            # compute_rankings hasn't run) -- skip rather than guess.
            skipped_no_rating += 1
            continue
 
        margin = expected_margin(home_rating.rating, away_rating.rating)
        model_prob = win_probability_from_margin(margin)
 
        line = _best_line(db, game.id)
        market_spread = line.spread if line else None
        market_home_ml = line.home_moneyline if line else None
        market_away_ml = line.away_moneyline if line else None
 
        implied_prob = _implied_home_prob(market_home_ml)
        delta = round(model_prob - implied_prob, 4) if implied_prob is not None else None
 
        games.append(
            GameOdds(
                game_id=game.cfbd_id,
                start_date=game.start_date or datetime.now(timezone.utc),
                home_team=home_school,
                away_team=away_school,
                model_predicted_margin=round(margin, 1),
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
            f"{skipped_no_rating} were skipped for missing PowerRating history on one/both teams -- "
            f"falling back to mock odds. Run `python -m scripts.compute_rankings --year {season} "
            f"--through-week {week - 1}` (from backend/) so ratings exist going into this week."
        )
        return _FALLBACK_ODDS
 
    return WeeklyOddsResponse(season=season, week=week, games=games)