"""
POST /api/matchup/simulate

Simulates one or more games between two teams using the offense and defense
ratings from the latest PowerRating snapshot -- the same snapshot
GET /api/rankings serves. The request picks where the game is played
(`location`: neutral site, team A at home, or team B at home) and how many
games to simulate (`num_games`). Every game is an independent random draw, so
calling it again gives new games. The method lives in app/simulation.py.
"""

import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PowerRating, Team
from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE
from app.schemas import (
    MatchupGame,
    MatchupLocation,
    MatchupRequest,
    MatchupSeriesSummary,
    MatchupSimulationResponse,
    MatchupTeamResult,
)
from app.simulation import load_sorted_scores, simulate_game

router = APIRouter(prefix="/api/matchup", tags=["matchup"])


def _load_rating(db: Session, team_id: int, season: int, week: int):
    """(Team, PowerRating) for `team_id` in the given snapshot, or an HTTP error."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    rating = (
        db.query(PowerRating)
        .filter(
            PowerRating.team_id == team_id,
            PowerRating.season == season,
            PowerRating.week == week,
        )
        .first()
    )
    if rating is None:
        raise HTTPException(status_code=404, detail=f"No power rating on file yet for {team.school}")
    if rating.offense_rating is None or rating.defense_rating is None:
        raise HTTPException(
            status_code=422,
            detail=f"{team.school} has no offense/defense rating yet, so it can't be simulated",
        )
    return team, rating


def _home_field_advantage(location: MatchupLocation) -> float:
    """
    Home edge from team A's side, in margin points, as simulate_game expects it:
    positive when A hosts, negative when B hosts, 0 at a neutral site.
    """
    if location == "team_a_home":
        return DEFAULT_HOME_FIELD_ADVANTAGE
    if location == "team_b_home":
        return -DEFAULT_HOME_FIELD_ADVANTAGE
    return 0.0


@router.post("/simulate", response_model=MatchupSimulationResponse)
def simulate_matchup(request: MatchupRequest, db: Session = Depends(get_db)):
    if request.team_a_id == request.team_b_id:
        raise HTTPException(status_code=422, detail="Pick two different teams")

    latest = (
        db.query(PowerRating.season, PowerRating.week)
        .order_by(PowerRating.season.desc(), PowerRating.week.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(status_code=404, detail="No power ratings have been computed yet")
    season, week = latest

    team_a, rating_a = _load_rating(db, request.team_a_id, season, week)
    team_b, rating_b = _load_rating(db, request.team_b_id, season, week)

    home_field_advantage = _home_field_advantage(request.location)

    # One RNG and one score table shared by every game in the request.
    rng = random.Random()
    sorted_scores = load_sorted_scores()
    sims = [
        simulate_game(
            rating_a.offense_rating,
            rating_a.defense_rating,
            rating_b.offense_rating,
            rating_b.defense_rating,
            sorted_scores=sorted_scores,
            rng=rng,
            home_field_advantage=home_field_advantage,
        )
        for _ in range(request.num_games)
    ]

    # simulate_game never returns a tie, so every game has exactly one winner.
    games = [
        MatchupGame(
            score_a=sim["score_a"],
            score_b=sim["score_b"],
            winner_team_id=team_a.id if sim["score_a"] > sim["score_b"] else team_b.id,
            overtime=sim["overtime"],
        )
        for sim in sims
    ]

    n = len(games)
    team_a_wins = sum(game.winner_team_id == team_a.id for game in games)
    summary = MatchupSeriesSummary(
        team_a_wins=team_a_wins,
        team_b_wins=n - team_a_wins,
        team_a_win_pct=round(100 * team_a_wins / n, 1),
        team_b_win_pct=round(100 * (n - team_a_wins) / n, 1),
        avg_score_a=round(sum(game.score_a for game in games) / n, 1),
        avg_score_b=round(sum(game.score_b for game in games) / n, 1),
        overtime_games=sum(game.overtime for game in games),
    )

    def result(team, rating, expected, score):
        return MatchupTeamResult(
            team_id=team.id,
            team=team.school,
            logo_url=team.logo_url,
            offense_rating=round(rating.offense_rating, 2),
            defense_rating=round(rating.defense_rating, 2),
            expected_points=round(expected, 1),
            score=score,
        )

    # Expected points are the same in every game (they depend only on the ratings
    # and the site), so the first game's values describe the whole series.
    first_sim, first_game = sims[0], games[0]

    return MatchupSimulationResponse(
        season=season,
        week=week,
        location=request.location,
        num_games=n,
        team_a=result(team_a, rating_a, first_sim["expected_a"], first_game.score_a),
        team_b=result(team_b, rating_b, first_sim["expected_b"], first_game.score_b),
        winner_team_id=first_game.winner_team_id,
        overtime=first_game.overtime,
        games=games,
        summary=summary,
    )
