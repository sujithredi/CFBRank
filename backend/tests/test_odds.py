"""GET /api/odds/weekly: every upcoming game is simulated 1,000 times and the results averaged."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.database import Base, get_db
from app.main import app
from app.models import Game, Line, PowerRating, Team
from app.routers import odds
from app.routers.odds import NUM_SIMULATIONS, simulate_matchup
from app.simulation import load_sorted_scores


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
    """Alabama (strong) hosts Auburn in week 8. Ratings are from week 6, going into the week."""
    db.add_all([
        Team(id=10, cfbd_id=1, school="Alabama", classification="fbs", logo_url="http://logos/alabama.png"),
        Team(id=20, cfbd_id=2, school="Auburn", classification="fbs"),  # no logo on file
    ])
    db.flush()
    db.add_all([
        PowerRating(team_id=10, season=2026, week=6, rating=15, rank=1, offense_rating=9.0, defense_rating=6.0),
        PowerRating(team_id=20, season=2026, week=6, rating=3, rank=2, offense_rating=1.0, defense_rating=2.0),
    ])
    db.add(Game(cfbd_id=3, season=2026, week=8, season_type="regular", completed=False,
                start_date=datetime(2026, 10, 24, 19, 0), home_team_id=10, away_team_id=20))
    db.commit()


def _games(client, **params):
    response = client.get("/api/odds/weekly", params=params)
    assert response.status_code == 200
    return response.json()


def _rating(offense, defense):
    return PowerRating(team_id=0, season=2026, week=1, rating=offense + defense,
                       offense_rating=offense, defense_rating=defense)


# ---- how the numbers are made ------------------------------------------------

def test_each_game_is_simulated_1000_times(client, seeded, monkeypatch):
    calls = []
    real = odds.simulate_game
    monkeypatch.setattr(odds, "simulate_game", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))

    body = _games(client)
    assert NUM_SIMULATIONS == 1000
    assert body["num_simulations"] == 1000
    assert len(body["games"]) == 1
    assert len(calls) == 1000


def test_the_model_numbers_are_averages_over_the_simulated_games(monkeypatch):
    # Four scripted games: home wins two of them.
    scripted = iter([(30, 20), (20, 31), (27, 24), (10, 17)])

    def fake_simulate_game(*args, **kwargs):
        score_a, score_b = next(scripted)
        return {"score_a": score_a, "score_b": score_b, "expected_a": 0, "expected_b": 0, "overtime": False}

    monkeypatch.setattr(odds, "simulate_game", fake_simulate_game)
    result = simulate_matchup(_rating(1, 1), _rating(1, 1), neutral_site=False, seed=1,
                              sorted_scores=None, num_simulations=4)
    assert result.home_win_prob == 0.5  # 2 of 4
    assert result.home_points == (30 + 20 + 27 + 10) / 4
    assert result.away_points == (20 + 31 + 24 + 17) / 4


def test_win_probability_is_the_share_of_the_1000_simulations_each_team_won(client, seeded):
    game = _games(client)["games"][0]
    wins = game["model_home_win_prob"] * NUM_SIMULATIONS
    assert wins == pytest.approx(round(wins), abs=1e-6)  # a whole number of the 1000 simulations
    assert 0 < wins < NUM_SIMULATIONS


def test_projected_points_margin_and_total_agree_with_each_other(client, seeded):
    game = _games(client)["games"][0]
    # Each is rounded to one decimal on its own, so they can differ by a rounding step.
    assert game["model_predicted_margin"] == pytest.approx(game["model_home_points"] - game["model_away_points"], abs=0.11)
    assert game["model_total"] == pytest.approx(game["model_home_points"] + game["model_away_points"], abs=0.11)


def test_the_better_home_team_is_favored_and_scores_more(client, seeded):
    game = _games(client)["games"][0]
    assert game["home_team"] == "Alabama" and game["away_team"] == "Auburn"
    assert game["model_home_win_prob"] > 0.7
    assert game["model_home_points"] > game["model_away_points"]
    assert game["model_predicted_margin"] > 0
    assert 30 < game["model_total"] < 80  # a real football total, not a rating gap


def test_a_game_shows_the_same_numbers_every_time_until_the_ratings_change(client, seeded):
    assert _games(client) == _games(client)


def test_changing_a_teams_rating_changes_the_numbers(client, seeded, db):
    before = _games(client)["games"][0]
    db.query(PowerRating).filter_by(team_id=20).update({"offense_rating": 11.0, "rating": 13.0})
    db.commit()
    after = _games(client)["games"][0]
    assert after["model_home_win_prob"] < before["model_home_win_prob"]
    assert after["model_away_points"] > before["model_away_points"]


# ---- where the game is played ------------------------------------------------

def test_the_home_team_gets_the_home_edge_unless_the_game_is_at_a_neutral_site():
    scores = load_sorted_scores()
    home, away = _rating(5, 5), _rating(5, 5)  # evenly matched, so any edge is the site
    at_home = simulate_matchup(home, away, neutral_site=False, seed=7, sorted_scores=scores)
    neutral = simulate_matchup(home, away, neutral_site=True, seed=7, sorted_scores=scores)

    # Same random draws, so the gap between them is the home-field edge (2.5 points of margin).
    assert 1.5 < (at_home.home_points - at_home.away_points) - (neutral.home_points - neutral.away_points) < 3.5
    assert at_home.home_win_prob > neutral.home_win_prob
    assert neutral.home_win_prob == pytest.approx(0.5, abs=0.06)


def test_a_neutral_site_game_is_simulated_without_the_home_edge(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"neutral_site": True})
    db.commit()
    game = _games(client)["games"][0]

    expected = simulate_matchup(_rating(9, 6), _rating(1, 2), neutral_site=True, seed=3, sorted_scores=load_sorted_scores())
    assert game["model_home_win_prob"] == round(expected.home_win_prob, 4)
    assert game["model_home_points"] == round(expected.home_points, 1)


# ---- logos, lines, ratings -----------------------------------------------------

def test_each_teams_logo_is_included_and_is_null_when_there_isnt_one(client, seeded):
    game = _games(client)["games"][0]
    assert game["home_logo_url"] == "http://logos/alabama.png"
    assert game["away_logo_url"] is None


def test_market_lines_come_through_and_the_delta_uses_the_simulated_win_probability(client, seeded, db):
    game_row_id = db.query(Game).filter_by(cfbd_id=3).one().id
    db.add(Line(game_id=game_row_id, provider="consensus", spread=-14.5, over_under=55.5,
                home_moneyline=-200, away_moneyline=170))
    db.commit()
    game = _games(client)["games"][0]

    assert game["market_spread"] == -14.5
    assert game["market_home_moneyline"] == -200 and game["market_away_moneyline"] == 170
    assert game["delta"] == pytest.approx(round(game["model_home_win_prob"] - 200 / 300, 4))


def test_a_game_without_a_line_has_no_market_numbers_or_delta(client, seeded):
    game = _games(client)["games"][0]
    assert game["market_spread"] is None and game["market_home_moneyline"] is None and game["delta"] is None


def test_only_ratings_from_before_the_week_are_used(client, seeded, db):
    before = _games(client, season=2026, week=8)["games"][0]
    # A rating computed *after* this week's games must not leak into this week's odds.
    db.add_all([
        PowerRating(team_id=10, season=2026, week=8, rating=-30, offense_rating=-15.0, defense_rating=-15.0),
        PowerRating(team_id=20, season=2026, week=8, rating=30, offense_rating=15.0, defense_rating=15.0),
    ])
    db.commit()
    assert _games(client, season=2026, week=8)["games"][0] == before


def test_a_game_is_skipped_when_a_team_has_no_offense_and_defense_rating(client, seeded, db):
    db.add_all([
        Team(id=30, cfbd_id=4, school="Old Snapshot", classification="fbs"),
        Team(id=40, cfbd_id=5, school="No Ratings", classification="fbs"),
    ])
    db.flush()
    db.add(PowerRating(team_id=30, season=2026, week=6, rating=4))  # from before the offense/defense split
    db.add_all([
        Game(cfbd_id=6, season=2026, week=8, season_type="regular", completed=False, home_team_id=30, away_team_id=10),
        Game(cfbd_id=7, season=2026, week=8, season_type="regular", completed=False, home_team_id=40, away_team_id=20),
    ])
    db.commit()

    games = _games(client)["games"]
    assert [(g["home_team"], g["away_team"]) for g in games] == [("Alabama", "Auburn")]


def test_completed_games_are_not_included(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"completed": True, "home_points": 31, "away_points": 10})
    db.add(Game(cfbd_id=8, season=2026, week=8, season_type="regular", completed=False, home_team_id=20, away_team_id=10))
    db.commit()
    games = _games(client, season=2026, week=8)["games"]
    assert [(g["home_team"], g["away_team"]) for g in games] == [("Auburn", "Alabama")]


def test_a_week_with_no_upcoming_games_gets_the_placeholder_rows(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"completed": True, "home_points": 31, "away_points": 10})
    db.commit()
    games = _games(client, season=2026, week=8)["games"]
    assert [g["away_team"] for g in games] == ["Wisconsin", "Kentucky"]


# ---- the placeholder rows ------------------------------------------------------

def test_with_no_games_on_file_the_placeholder_rows_have_every_field(client):
    body = _games(client)
    assert body["num_simulations"] == NUM_SIMULATIONS
    assert len(body["games"]) == 2
    for game in body["games"]:
        for field in ("model_home_points", "model_away_points", "model_predicted_margin", "model_total",
                      "model_home_win_prob", "home_logo_url", "away_logo_url"):
            assert field in game
        assert game["model_predicted_margin"] == pytest.approx(game["model_home_points"] - game["model_away_points"], abs=0.11)
        assert game["model_total"] == pytest.approx(game["model_home_points"] + game["model_away_points"], abs=0.11)
