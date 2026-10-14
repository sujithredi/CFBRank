"""Tests for app/simulation.py and POST /api/matchup/simulate."""

import random

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app import simulation
from app.database import Base, get_db
from app.main import app
from app.models import Conference, PowerRating, Team
from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE
from app.schemas import MAX_SIMULATED_GAMES
from app.simulation import (
    LEAGUE_AVG_POINTS,
    expected_points,
    load_sorted_scores,
    simulate_game,
    simulate_team_score,
)


# ---- simulation.py ---------------------------------------------------------

def test_expected_points_subtracts_the_opponents_defense():
    # Good defense (positive rating) holds the other team down.
    assert expected_points(5.0, 3.0) == pytest.approx(LEAGUE_AVG_POINTS + 2.0)
    assert expected_points(0.0, 0.0) == LEAGUE_AVG_POINTS


def test_historical_scores_load_sorted():
    scores = load_sorted_scores()
    assert len(scores) > 1000
    assert np.all(np.diff(scores) >= 0)


def test_simulated_scores_are_real_historical_scores():
    scores = load_sorted_scores()
    allowed = set(scores.tolist())
    rng = random.Random(1)
    for _ in range(500):
        assert simulate_team_score(30.0, scores, rng) in allowed


def test_same_seed_gives_same_game():
    a = simulate_game(10, 5, -3, 2, rng=random.Random(42))
    b = simulate_game(10, 5, -3, 2, rng=random.Random(42))
    assert a == b


def test_simulated_average_tracks_expected_points():
    # Over many games a team's mean score should sit near what the model expects
    # for league-average inputs (~26.4), and clearly higher for a stronger offense.
    rng = random.Random(7)
    scores = load_sorted_scores()
    average = np.mean([simulate_team_score(26.4, scores, rng) for _ in range(4000)])
    strong = np.mean([simulate_team_score(40.0, scores, rng) for _ in range(4000)])
    assert abs(average - 26.4) < 1.5
    assert strong > average + 5


def test_a_tie_goes_to_overtime_and_is_never_returned_as_a_tie():
    # A one-score history forces both teams to the same score every time.
    flat = np.array([20, 20, 20])
    rng = random.Random(3)
    for _ in range(50):
        game = simulate_game(0, 0, 0, 0, sorted_scores=flat, rng=rng)
        assert game["overtime"] is True
        assert game["score_a"] != game["score_b"]
        assert sorted([game["score_a"], game["score_b"]]) == [20, 23]


def test_no_overtime_flag_on_a_regulation_game():
    scores = np.arange(0, 80)
    rng = random.Random(5)
    for _ in range(200):
        game = simulate_game(20, 10, -20, -10, sorted_scores=scores, rng=rng)
        if game["score_a"] != game["score_b"]:
            assert game["overtime"] is False


def test_home_field_advantage_is_split_across_both_teams_expected_points():
    neutral = simulate_game(10, 5, -3, 2, rng=random.Random(1))
    a_home = simulate_game(10, 5, -3, 2, rng=random.Random(1), home_field_advantage=4.0)
    b_home = simulate_game(10, 5, -3, 2, rng=random.Random(1), home_field_advantage=-4.0)

    assert a_home["expected_a"] == pytest.approx(neutral["expected_a"] + 2.0)
    assert a_home["expected_b"] == pytest.approx(neutral["expected_b"] - 2.0)
    assert b_home["expected_a"] == pytest.approx(neutral["expected_a"] - 2.0)
    assert b_home["expected_b"] == pytest.approx(neutral["expected_b"] + 2.0)


def test_hosting_raises_a_teams_win_rate():
    # Identical teams: neutral is a coin flip, hosting should tip it toward the host.
    scores = load_sorted_scores()

    def team_a_win_rate(hfa):
        rng = random.Random(11)
        games = [simulate_game(0, 0, 0, 0, sorted_scores=scores, rng=rng, home_field_advantage=hfa)
                 for _ in range(5000)]
        return sum(g["score_a"] > g["score_b"] for g in games) / len(games)

    neutral, hosting, visiting = (team_a_win_rate(h) for h in
                                  (0.0, DEFAULT_HOME_FIELD_ADVANTAGE, -DEFAULT_HOME_FIELD_ADVANTAGE))
    assert abs(neutral - 0.5) < 0.03
    assert hosting > neutral + 0.02
    assert visiting < neutral - 0.02


# ---- endpoint --------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)  # no `with`: skips the lifespan, so the real DB is never touched
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db):
    sec = Conference(id=1, cfbd_id=8, name="SEC")
    db.add(sec)
    db.flush()
    db.add_all([
        Team(id=10, cfbd_id=333, school="Alabama", logo_url="https://example.com/333.png", conference_id=1),
        Team(id=20, cfbd_id=999, school="Wisconsin", conference_id=1),
        Team(id=30, cfbd_id=998, school="No Split U", conference_id=1),
        Team(id=40, cfbd_id=997, school="Old Snapshot U", conference_id=1),
    ])
    db.flush()
    db.add_all([
        PowerRating(team_id=10, season=2026, week=6, rating=15.0, rank=1, wins=5, losses=0,
                    offense_rating=9.0, defense_rating=6.0),
        PowerRating(team_id=20, season=2026, week=6, rating=-2.0, rank=2, wins=2, losses=3,
                    offense_rating=-4.0, defense_rating=2.0),
        # Pre-split snapshot row: has an overall rating but no offense/defense.
        PowerRating(team_id=30, season=2026, week=6, rating=1.0, rank=3, wins=3, losses=2),
        # Only rated in an earlier week, so absent from the latest snapshot.
        PowerRating(team_id=40, season=2026, week=5, rating=0.0, rank=4, wins=3, losses=2,
                    offense_rating=0.0, defense_rating=0.0),
    ])
    db.commit()


def _post(client, a, b, **options):
    return client.post("/api/matchup/simulate", json={"team_a_id": a, "team_b_id": b, **options})


def test_simulate_returns_a_complete_game(client, seeded):
    response = _post(client, 10, 20)
    assert response.status_code == 200
    body = response.json()

    assert (body["season"], body["week"]) == (2026, 6)
    a, b = body["team_a"], body["team_b"]
    assert (a["team"], b["team"]) == ("Alabama", "Wisconsin")
    assert a["logo_url"] == "https://example.com/333.png"
    assert b["logo_url"] is None

    # expected = 26.4 + own offense - opponent defense
    assert a["expected_points"] == pytest.approx(26.4 + 9.0 - 2.0)
    assert b["expected_points"] == pytest.approx(26.4 - 4.0 - 6.0)

    historical = set(load_sorted_scores().tolist())
    assert a["score"] != b["score"]
    if not body["overtime"]:
        assert a["score"] in historical and b["score"] in historical

    expected_winner = a if a["score"] > b["score"] else b
    assert body["winner_team_id"] == expected_winner["team_id"]


def test_simulate_is_random_between_calls(client, seeded):
    results = {tuple(sorted((r["team_a"]["score"], r["team_b"]["score"]))) for r in
               (_post(client, 10, 20).json() for _ in range(30))}
    assert len(results) > 1


def test_better_team_wins_more_often(client, seeded):
    wins = sum(_post(client, 10, 20).json()["winner_team_id"] == 10 for _ in range(60))
    assert wins > 35  # Alabama has a ~15-point rating edge


def test_same_team_twice_is_rejected(client, seeded):
    assert _post(client, 10, 10).status_code == 422


def test_unknown_team_is_404(client, seeded):
    assert _post(client, 10, 9999).status_code == 404


def test_team_missing_from_latest_snapshot_is_404(client, seeded):
    assert _post(client, 10, 40).status_code == 404


def test_team_without_offense_defense_split_is_422(client, seeded):
    response = _post(client, 10, 30)
    assert response.status_code == 422
    assert "No Split U" in response.json()["detail"]


def test_no_ratings_at_all_is_404(client):
    assert _post(client, 1, 2).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"team_a_id": 10}, {"team_a_id": 0, "team_b_id": 20},
                                     {"team_a_id": "x", "team_b_id": 20}])
def test_bad_request_bodies_are_422(client, seeded, payload):
    assert client.post("/api/matchup/simulate", json=payload).status_code == 422


# ---- location and number of games -----------------------------------------

def test_defaults_are_one_neutral_site_game(client, seeded):
    body = _post(client, 10, 20).json()
    assert body["location"] == "neutral"
    assert body["num_games"] == 1
    assert len(body["games"]) == 1
    assert body["summary"]["team_a_wins"] + body["summary"]["team_b_wins"] == 1


@pytest.mark.parametrize("location, shift", [
    ("neutral", 0.0),
    ("team_a_home", DEFAULT_HOME_FIELD_ADVANTAGE / 2),
    ("team_b_home", -DEFAULT_HOME_FIELD_ADVANTAGE / 2),
])
def test_location_shifts_each_teams_expected_points(client, seeded, location, shift):
    body = _post(client, 10, 20, location=location).json()
    assert body["location"] == location
    # Half the home edge goes to the host and half comes off the visitor.
    assert body["team_a"]["expected_points"] == pytest.approx(26.4 + 9.0 - 2.0 + shift, abs=0.051)
    assert body["team_b"]["expected_points"] == pytest.approx(26.4 - 4.0 - 6.0 - shift, abs=0.051)


def test_num_games_returns_that_many_games_with_a_consistent_summary(client, seeded):
    body = _post(client, 10, 20, num_games=50, location="team_b_home").json()
    games, summary = body["games"], body["summary"]

    assert body["num_games"] == 50
    assert len(games) == 50
    assert all(g["score_a"] != g["score_b"] for g in games)
    assert all(g["winner_team_id"] == (10 if g["score_a"] > g["score_b"] else 20) for g in games)

    a_wins = sum(g["winner_team_id"] == 10 for g in games)
    assert summary["team_a_wins"] == a_wins
    assert summary["team_b_wins"] == 50 - a_wins
    assert summary["team_a_win_pct"] == pytest.approx(100 * a_wins / 50, abs=0.05)
    assert summary["team_a_win_pct"] + summary["team_b_win_pct"] == pytest.approx(100, abs=0.1)
    assert summary["avg_score_a"] == pytest.approx(sum(g["score_a"] for g in games) / 50, abs=0.05)
    assert summary["avg_score_b"] == pytest.approx(sum(g["score_b"] for g in games) / 50, abs=0.05)
    assert summary["overtime_games"] == sum(g["overtime"] for g in games)


def test_top_level_game_fields_describe_the_first_game(client, seeded):
    body = _post(client, 10, 20, num_games=5).json()
    first = body["games"][0]
    assert body["team_a"]["score"] == first["score_a"]
    assert body["team_b"]["score"] == first["score_b"]
    assert body["winner_team_id"] == first["winner_team_id"]
    assert body["overtime"] == first["overtime"]


def test_games_in_a_series_are_independent_draws(client, seeded):
    games = _post(client, 10, 20, num_games=60).json()["games"]
    assert len({(g["score_a"], g["score_b"]) for g in games}) > 1


def test_better_team_wins_most_of_a_long_series_even_on_the_road(client, seeded):
    body = _post(client, 10, 20, num_games=200, location="team_b_home").json()
    assert body["summary"]["team_a_win_pct"] > 60


def test_the_maximum_number_of_games_is_allowed(client, seeded):
    response = _post(client, 10, 20, num_games=MAX_SIMULATED_GAMES)
    assert response.status_code == 200
    assert len(response.json()["games"]) == MAX_SIMULATED_GAMES


@pytest.mark.parametrize("options", [
    {"num_games": 0},
    {"num_games": -3},
    {"num_games": MAX_SIMULATED_GAMES + 1},
    {"num_games": 2.5},
    {"num_games": "many"},
    {"location": "home"},
    {"location": ""},
    {"location": None},
])
def test_bad_location_or_game_count_is_422(client, seeded, options):
    assert _post(client, 10, 20, **options).status_code == 422
